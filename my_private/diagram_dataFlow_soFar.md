
```mermaid
flowchart LR
    Env[".env / Environment"] --> Config["load_settings()"]
    Config --> Subscriber["SparkplugSubscriber"]
    MQTT[(MQTT Broker)] -->|Sparkplug frames| Subscriber
    Subscriber --> AliasCache["Alias Cache JSON"]
    Subscriber --> Normalize["Normalize Device & Metric Paths"]
    Normalize --> Decision{DB_MODE == "local"?}
    Decision -->|No| JSONL["JSONL fallback"]
    Decision -->|Yes| Repo["MetadataRepository"]
    Repo <--> Postgres[(PostgreSQL uns_metadata)]
```

```mermaid
flowchart LR
    %% Entry
    Broker[(MQTT Broker)]
    Env[".env / Environment"]

    %% Config
    subgraph Config["Configuration"]
      CFG["src/uns_metadata_sync/config.py::load_settings()"]
      ENV[".env (MQTT_*, PG*, DB_MODE)"]
      ENV --> CFG
    end

    %% Runtime / Ingress
    subgraph Ingress["Runtime / Ingress"]
      SUB["src/uns_metadata_sync/service.py::SparkplugSubscriber"]
      DECODE["src/uns_metadata_sync/sparkplug_b_utils.py::decode_sparkplug_payload()"]
      ALIAS["src/uns_metadata_sync/alias_cache.py (load/save)"]
      NORM["src/uns_metadata_sync/path_normalizer.py (normalize_* / canary_id)"]
      Broker -->|Sparkplug frames| SUB
      CFG --> SUB
      SUB --> ALIAS
      SUB --> DECODE --> NORM
    end

    %% Persistence
    subgraph DB["Persistence (PostgreSQL)"]
      CONN["src/uns_metadata_sync/db/__init__.py::connect_from_settings()"]
      REPO["src/uns_metadata_sync/db/repository.py::MetadataRepository\n- upsert_device()\n- upsert_metric()\n- upsert_metric_property()"]
      MIG["src/uns_metadata_sync/migrations (sql/*.sql, runner.py)\n- 000 ledger\n- 001 schema + publication"]
      SUB -->|DB_MODE == 'local'| REPO
      CFG --> CONN --> REPO
      REPO <--> PG[(uns_metadata DB\nschema: uns_meta)]
      MIG --> PG
    end

    %% CDC / Historian
    subgraph CDC["Change Data Capture / Historian"]
      PUB["Postgres Publication: uns_meta_pub\n(tables: metrics, metric_properties)"]
      HIST["Historian / Downstream CDC Consumers"]
      PG --> PUB --> HIST
    end

    %% JSONL fallback (non-blocking)
    JSONL["Optional JSONL sink\n(messages_{topic}.jsonl)"]
    SUB -->|write_jsonl=true| JSONL
```