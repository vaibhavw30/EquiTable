# ─────────────────────────────────────────────────────────────────────────────
# Remote state with locking.
#
# COMMENTED BY DEFAULT — deliberately. Uncommenting and running `terraform init`
# creates real AWS resources and starts billing (a few cents/month), and state
# that lives in a bucket someone else has to create is a bad default for a repo
# that someone might clone and run.
#
# Local state is the default so `terraform plan` works offline for review. That
# is fine for one operator on one laptop and NOT fine the moment a second person
# or a CI job can apply — concurrent applies against unlocked state corrupt it.
#
# ── Bootstrap (once, before uncommenting) ───────────────────────────────────
#
#   aws s3api create-bucket --bucket equitable-tfstate-094009462978 \
#     --region us-east-1
#   aws s3api put-bucket-versioning --bucket equitable-tfstate-094009462978 \
#     --versioning-configuration Status=Enabled
#   aws s3api put-bucket-encryption --bucket equitable-tfstate-094009462978 \
#     --server-side-encryption-configuration \
#     '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
#   aws s3api put-public-access-block --bucket equitable-tfstate-094009462978 \
#     --public-access-block-configuration \
#     'BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true'
#
# Versioning is not optional: state is the only record of what Terraform
# believes exists, and a corrupted or truncated write with no version history
# means rebuilding it by hand with `terraform import`.
#
# `use_lockfile = true` uses S3's own conditional writes for locking
# (Terraform >= 1.11), which replaces the DynamoDB lock table the older pattern
# required — one less resource to create, pay for, and forget to clean up.
#
# terraform {
#   backend "s3" {
#     bucket       = "equitable-tfstate-094009462978"
#     key          = "equitable/terraform.tfstate"
#     region       = "us-east-1"
#     encrypt      = true
#     use_lockfile = true
#   }
# }
