terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.50.0"
    }
  }

  backend "s3" {
    bucket  = "terraform-state-o1r8"
    key     = "ctdl-xtra/envs/shared/tfstate"
    region  = "us-east-1"
    encrypt = true
  }
}

provider "aws" {
  region = "us-east-1"

  default_tags {
    tags = {
      project    = "ctdl-xtra"
      managed-by = "terraform"
    }
  }
}
