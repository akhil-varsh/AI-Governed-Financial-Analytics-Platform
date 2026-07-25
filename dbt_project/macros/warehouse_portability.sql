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

{# Null-safe cast to a LOGICAL type, mapped to each engine's physical type and
   null-safe function. Callers pass a logical type (integer/float/numeric/date/
   timestamp/string), never a vendor type name, so the same model runs on both
   BigQuery and DuckDB. BigQuery uses SAFE_CAST; DuckDB/ANSI use TRY_CAST. #}
{% macro try_cast(column, logical_type) -%}
    {%- set type_map = {
        'bigquery': {'integer': 'INT64', 'float': 'FLOAT64', 'numeric': 'NUMERIC',
                     'date': 'DATE', 'timestamp': 'TIMESTAMP', 'string': 'STRING'},
        'default':  {'integer': 'BIGINT', 'float': 'DOUBLE', 'numeric': 'DECIMAL(38,9)',
                     'date': 'DATE', 'timestamp': 'TIMESTAMP', 'string': 'VARCHAR'}
    } -%}
    {%- set dialect = 'bigquery' if target.type == 'bigquery' else 'default' -%}
    {%- set physical = type_map[dialect][logical_type] -%}
    {%- if target.type == 'bigquery' -%}
        SAFE_CAST({{ column }} AS {{ physical }})
    {%- else -%}
        TRY_CAST({{ column }} AS {{ physical }})
    {%- endif -%}
{%- endmacro %}

{# Cast to the engine's string type (BigQuery STRING vs DuckDB VARCHAR). #}
{% macro to_string(column) -%}
    {%- if target.type == 'bigquery' -%}
        CAST({{ column }} AS STRING)
    {%- else -%}
        CAST({{ column }} AS VARCHAR)
    {%- endif -%}
{%- endmacro %}

{# Full month / weekday name, and a weekend flag — vendor-specific formatting. #}
{% macro month_name(column) -%}
    {%- if target.type == 'bigquery' -%}
        FORMAT_DATE('%B', {{ column }})
    {%- else -%}
        MONTHNAME({{ column }})
    {%- endif -%}
{%- endmacro %}

{% macro day_name(column) -%}
    {%- if target.type == 'bigquery' -%}
        FORMAT_DATE('%A', {{ column }})
    {%- else -%}
        DAYNAME({{ column }})
    {%- endif -%}
{%- endmacro %}

{% macro is_weekend(column) -%}
    {%- if target.type == 'bigquery' -%}
        EXTRACT(DAYOFWEEK FROM {{ column }}) IN (1, 7)
    {%- else -%}
        EXTRACT(DOW FROM {{ column }}) IN (0, 6)
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
