variable "aws_region" {
  description = "AWS region for the chatbot deployment."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Name prefix for AWS resources."
  type        = string
  default     = "meridian-support-chatbot"
}

variable "image_tag" {
  description = "Container image tag to deploy from ECR."
  type        = string
  default     = "latest"
}

variable "mcp_server_url" {
  description = "Meridian MCP server URL."
  type        = string
  default     = "https://order-mcp-74afyau24q-uc.a.run.app/mcp"
}

variable "llm_model" {
  description = "Cost-effective LLM model name."
  type        = string
  default     = "gpt-4o-mini"
}

variable "openai_api_key" {
  description = "OpenAI-compatible API key used by the backend."
  type        = string
  sensitive   = true
}
