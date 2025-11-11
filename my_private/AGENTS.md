# AGENTS.md — Metadata Sync Microservice (UNS)

> Guia para humanos e agentes ao contribuir para este repositório.
> **Escopo:** todo o directório onde este ficheiro está e subpastas.
> **Prioridade:** ficheiros `AGENTS.md` mais profundos prevalecem em caso de conflito.

## 0) Contexto do projecto (normativo)
- **Objectivo:** Ingerir DBIRTH (Sparkplug B) do EMQX, normalizar identidades UNS, persistir metadados em PostgreSQL e propagar **apenas diffs** para o Canary via Write API.
- **Domínio de dados (PostgreSQL / schema `uns_meta`):**
  - Tabelas: `devices`, `metrics`, `metric_properties` (com enum estrito `spb_property_type`), `metric_versions` (audit diff), `metric_path_lineage` (rename lineage).
  - `metrics.canary_id` = `uns_path` substituindo `/` por `.` (coluna gerada).
  - Unicidade: `devices` por `(group_id, edge, device)` e `uns_path` único; `metrics` por `(device_id, name)` e `uns_path` único.
- **CDC:** Publicação **`uns_meta_pub`** para **`metrics` e `metric_properties`** (escopo mínimo). *Nota:* alinhar documentação externa para evitar divergências.
- **Limites operacionais:** Debounce de **3 minutos** após refresh do Transmitter; rate‑limit **≤ 500 req/s** para Canary; retries com exponential backoff + jitter; circuit breaker.
- **Segurança:** TLS 1.3 a EMQX/DB/Canary; segredos em `.env` (perms 600).

## 1) Regras Git (obrigatórias)
- **Não criar branches novas** para tarefas automatizadas (Codex‑1). Trabalhar na branch actual.
- **Não reescrever histórico** (`commit --amend`, rebase destrutivo proibidos).
- **Só código *commitado* é avaliado.** Esperar cada comando terminar antes de continuar.
- Confirmar *worktree* limpa: `git status` antes de concluir.

### Mensagens de commit
```
<tipo>: <resumo curto no imperativo>

[Contexto adicional]
Refs: #<issue>
```
**Tipos:** feat, fix, docs, refactor, test, chore, perf.

## 2) Testes e Qualidade (test‑first)
**Obrigatório definir/actualizar testes ANTES do código:**
- **Unit:** parsing/normalização de UNS; tipagem de propriedades (`int|long|float|double|string|boolean`); upsert idempotente; diff computation; utilitários de retry/backoff.
- **Integração:** MQTT ingest → DB; DB → CDC listener; CDC → Canary client.
- **Contrato:** decode Sparkplug (binário + JSON fixtures); shape request/response Canary.
- **E2E:** EMQX → Serviço → Postgres → CDC → Serviço → Canary.
- **Integridade:** unicidade/constraints, triggers `updated_at`, coluna gerada `canary_id`, lineage/versions.
- **Não‑funcionais:** performance, rate‑limit, resiliência (retries/circuit), segurança (TLS/auth), observabilidade.

### Comandos padrão
```bash
# Python
uv run ruff check .
uv run pytest -q
```

## 3) Estilo e Convenções
- **Formatter/lint:** seguir o que a configuração do repo definir (Black/Ruff, etc.).
- **UNS identity & naming:**
  - `Secil/<Country>/<Business Unit>/<Plant>/<...>/<Metric>` (slash‑separated).
  - **Canary tag id:** substituir `/` por `.` (dot‑separated).
- **Propriedades Sparkplug (typed):**
  - Armazenar cada `key` em `metric_properties` com tipo estrito (`spb_property_type`) e **apenas uma** coluna de valor preenchida por linha.

## 4) Integrações e Limites (dever de conformidade)
- **EMQX (ingest):** subscrição **`spBv1.0/Secil/DBIRTH/#`**, QoS 0, clean session true, TLS 1.3 (username/password).
- **CDC:** publicação `uns_meta_pub` (tabelas: `metrics`, `metric_properties`); listener traduz para diffs com **debounce 180 s**.
- **Canary:** `POST /api/v2/storeTagData`, **≤ 500 req/s**, retries (6 tentativas) com backoff exponencial + jitter; circuit breaker e recuperação half‑open.

## 5) Observabilidade e Logs
- **Prometheus:** contadores para DBIRTHs processados, metrics parsed, upserts, CDC diffs, Canary ok/fail, retries; tempos p50/p95; *gauge* de backlog/queue e estado do circuito.
- **Logs:** JSON estruturado; sem segredos; rotação diária/100 MB; retenção 14 dias.
- **Watchdogs:** publicar eventos de saúde para namespace MQTT vanilla (Ignition Cloud).

## 6) Segurança, Segredos e Dados
- TLS 1.3 end‑to‑end; Postgres com `verify-full`.
- `.env` com permissões 600; **nunca** comitar credenciais.
- Utilizadores dedicados: `uns_meta_app` (RW) e `uns_meta_cdc` (replication).

## 7) Pull Requests
- **Pequenas e focadas** (< 300 linhas quando possível).
- Incluir: resumo, screenshots/logs (se relevante), *checklist* abaixo, links para doc/issue.
- **Título PR =** melhor commit.

### Checklist PR
- [ ] Testes locais passam (unit/integration/contract/e2e conforme aplicável)
- [ ] Lint/format sem erros
- [ ] Sem violações de unicidade/constraints na DB
- [ ] Respeita debounce de 3 min e rate‑limit ≤ 500 rps
- [ ] Segurança/segredos revistos; TLS configurado
- [ ] Observabilidade cobre métricas essenciais
- [ ] Documentação (`docs/`) e changelog actualizados

## 8) Estrutura de Pastas (referência)
```
src/                # serviço
tests/              # unit, integration, contract, e2e
docs/               # design, schema/ERD, testing spec
scripts/            # tooling (mocks, fixtures, helpers)
```

## 9) Regras por directório (exemplos)
- `src/ingest/**`: proibir `print`; usar logging estruturado; tipagem explícita.
- `src/cdc/**`: testes de debounce e ordem cronológica obrigatórios.
- `src/canary/**`: respeitar rate‑limit e retries com jitter; circuit breaker com métricas.
- `tests/fixtures/**`: incluir bin e JSON de DBIRTH realistas; determinismo garantido.

## 10) Tarefas automatizadas (sugerido)
- CI: lint + testes + relatório cobertura; validação de constraints com queries de verificação; SCA de dependências.
- Protecção de branch: impedir merge sem checks verdes.

## 11) Notas para Codex‑1
- Não criar branches; não alterar commits existentes; **commitar** todas as mudanças.
- Executar todos os testes referidos (podes saltar apenas se a tarefa o permitir explicitamente).
- Confirmar `git status` limpo antes de terminar.

---

> Última atualização: YYYY‑MM‑DD
