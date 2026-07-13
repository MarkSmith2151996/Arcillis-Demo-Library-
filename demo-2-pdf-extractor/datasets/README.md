# Invoice Evaluation Dataset

## Source And License

The invoice evaluation data is downloaded on demand from the
[Katana ML invoices-donut-data-v1 dataset](https://huggingface.co/datasets/katanaml-org/invoices-donut-data-v1).
It is the Sparrow Invoice Dataset, prepared by Katana ML from the Samples of
electronic invoices dataset. The dataset card declares an MIT license.

The downloaded `donut-invoices/` directory is intentionally ignored by Git.
Download it with `huggingface_hub.snapshot_download` using the repository ID
`katanaml-org/invoices-donut-data-v1`.

## Layout

The Hugging Face revision ships three Parquet shards under `data/`. For the
evaluation harness, those shards are materialized into the following layout:

```text
donut-invoices/
  train/
    images/*.jpg
    metadata.jsonl
  test/
    images/*.jpg
    metadata.jsonl
  validation/
    images/*.jpg
    metadata.jsonl
```

Each JSONL record has a `file_name` relative to its split directory and a
`gt_parse` object. `gt_parse.header` contains `invoice_no`, `invoice_date`,
`seller`, `client`, `seller_tax_id`, `client_tax_id`, and `iban`.
`gt_parse.items` is an array of line items with `item_desc`, `item_qty`,
`item_net_price`, `item_net_worth`, `item_vat`, and `item_gross_worth`.
`gt_parse.summary` contains `total_net_worth`, `total_vat`, and
`total_gross_worth`.

## Evaluation Use

For each invoice image, the PDF extractor produces structured output. The
evaluation harness compares that output with the corresponding `gt_parse`
record to calculate field-level extraction accuracy.
