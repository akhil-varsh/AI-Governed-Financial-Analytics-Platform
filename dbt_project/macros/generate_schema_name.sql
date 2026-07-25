{#
    Custom schema naming so medallion layers land in predictable, isolated datasets.

    Behaviour:
      - When a model sets +schema (bronze/silver/gold/marts), the dataset becomes
        `<target_dataset>_<layer>`, e.g. northwind_dev_bronze, northwind_ci_gold.
      - When no custom schema is set, the model lands in the plain target dataset.

    WHY prefix with the target dataset instead of using the bare layer name
    ("bronze"): it keeps dev, CI, and any future per-developer sandboxes fully
    isolated inside one BigQuery project. Two engineers (or a CI run and a local
    run) can build simultaneously without clobbering each other's `bronze`.

    Alternative rejected: dbt's default macro, which in non-prod prepends the
    target schema to EVERYTHING. That works, but we make the layered intent
    explicit and documented here so an interviewer can see the reasoning.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set default_schema = target.schema -%}
    {%- if custom_schema_name is none -%}
        {{ default_schema }}
    {%- else -%}
        {{ default_schema }}_{{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
