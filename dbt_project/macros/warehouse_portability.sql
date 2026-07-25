{#
    Warehouse-portability seam.

    Requirement: keep the SQL ANSI-compliant and isolate any warehouse-specific
    syntax in ONE place, so migrating BigQuery -> Snowflake is a small, auditable
    diff rather than a hunt-and-peck through every model.

    Rule for the rest of the project: models must call these macros instead of
    writing vendor functions inline. If you ever type `SAFE_CAST`, `PARSE_DATE`,
    `GENERATE_UUID`, `CURRENT_DATETIME`, or a backtick-quoted identifier in a
    model, it belongs behind a macro here instead.
#}

{# Ingestion/build timestamp in UTC. BigQuery: CURRENT_TIMESTAMP(); Snowflake
   would swap to SYSDATE()/CURRENT_TIMESTAMP with no model changes. #}
{% macro load_timestamp() -%}
    {%- if target.type == 'bigquery' -%}
        CURRENT_TIMESTAMP()
    {%- elif target.type == 'snowflake' -%}
        CONVERT_TIMEZONE('UTC', CURRENT_TIMESTAMP())
    {%- else -%}
        CURRENT_TIMESTAMP
    {%- endif -%}
{%- endmacro %}

{# Null-safe cast. BigQuery has SAFE_CAST; ANSI/Snowflake use TRY_CAST. #}
{% macro try_cast(column, type) -%}
    {%- if target.type == 'bigquery' -%}
        SAFE_CAST({{ column }} AS {{ type }})
    {%- else -%}
        TRY_CAST({{ column }} AS {{ type }})
    {%- endif -%}
{%- endmacro %}

{# A far-future sentinel for open SCD2 rows (valid_to). Centralised so every
   SCD2 model uses the identical high-date and downstream BETWEEN logic is safe. #}
{% macro scd_end_of_time() -%}
    CAST('9999-12-31' AS DATE)
{%- endmacro %}

{# Truncate a date to the first of its month. BigQuery takes the part as a bare
   keyword AFTER the column; Snowflake/DuckDB take it as a quoted string BEFORE. #}
{% macro date_trunc_month(column) -%}
    {%- if target.type == 'bigquery' -%}
        DATE_TRUNC({{ column }}, MONTH)
    {%- else -%}
        DATE_TRUNC('month', {{ column }})
    {%- endif -%}
{%- endmacro %}
