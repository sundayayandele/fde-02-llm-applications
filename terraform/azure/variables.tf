variable "subscription_id" {
  description = "Azure subscription for the lab (use a sandbox subscription)."
  type        = string
}

variable "location" {
  description = "Azure region. westeurope (Netherlands) or northeurope (Ireland) keep data in the EU."
  type        = string
  default     = "westeurope"
}

variable "app_name" {
  description = "Name used for every resource."
  type        = string
  default     = "fde-02-llm-applications"
}

variable "image_tag" {
  description = "Image tag pushed to the registry created here."
  type        = string
  default     = "1.1.0"
}

variable "deploy_app" {
  description = "Create the Container App. Set false on the first apply, push the image, then set true."
  type        = bool
  default     = false
}

variable "mistral_api_key" {
  description = "Stored in Key Vault, read by the Container App through its managed identity."
  type        = string
  sensitive   = true
  default     = "set-me"
}

variable "monthly_budget_usd" {
  description = "Monthly budget for the lab resource group; alerts at 50, 80 and 100 percent."
  type        = number
  default     = 50
}

variable "budget_start_date" {
  description = "First day of the current month, RFC 3339 (Azure requires the first of a month)."
  type        = string
  default     = "2026-10-01T00:00:00Z"
}

variable "alert_email" {
  description = "Email that receives budget alerts."
  type        = string
}
