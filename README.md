# Meridian Electronics Support Chatbot

Production-minded prototype for the AI Engineer Assessment. The app uses a React frontend, FastAPI backend, a cost-effective OpenAI-compatible model, and Meridian's MCP server for tool-grounded customer support workflows.

## Architecture

- React renders the customer chat UI.
- FastAPI owns sessions, safety checks, and the `/api/chat` endpoint.
- The agent discovers tools from the MCP server and exposes them to the LLM as callable functions.
- Business facts and actions come from MCP tools, not model memory.
- Docker packages the React build and API into one deployable container.
- Terraform deploys the container to AWS App Runner with ECR and Secrets Manager.

## Local Setup

```bash
cp .env.example .env
pip install -r requirements.txt
```

Set `OPENAI_API_KEY` in `.env`.

Run the backend:

```bash
uvicorn app:app --reload --port 8000
```

Run the React frontend:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Docker

```bash
docker build -t meridian-support-chatbot .
docker run --env-file .env -p 8000:8000 meridian-support-chatbot
```

Open `http://localhost:8000`.

## Tests

```bash
pytest
cd frontend
npm install
npm run build
```

## AWS Deployment

Terraform deploys:

- ECR repository
- App Runner service
- IAM roles for ECR access and runtime secrets
- Secrets Manager secret for `OPENAI_API_KEY`
- CloudWatch log group

Manual deployment:

```bash
cd terraform
terraform init
terraform apply \
  -var="openai_api_key=$OPENAI_API_KEY" \
  -var="image_tag=latest"
```

The GitHub Actions deployment workflow expects these repository secrets:

- `AWS_DEPLOY_ROLE_ARN`: IAM role GitHub Actions can assume through OIDC.
- `OPENAI_API_KEY`: OpenAI-compatible API key used by the backend.

The deployment workflow first ensures ECR exists, then builds and pushes the Docker image, then applies the full Terraform stack to App Runner.

## Important Safety Behavior

- The assistant must use MCP tools for inventory, orders, customer data, and authentication.
- Write operations such as order creation require explicit customer confirmation.
- Tool arguments are validated and sensitive values are redacted from logs.
- The frontend never receives LLM provider credentials or direct MCP access.

## Key Files

- `app.py`: FastAPI entrypoint and static React serving.
- `meridian_chatbot/agent.py`: LLM and MCP orchestration.
- `meridian_chatbot/mcp_client.py`: Streamable HTTP MCP integration.
- `frontend/src/main.tsx`: React chat UI.
- `terraform/`: AWS App Runner infrastructure.
- `.github/workflows/`: CI and AWS deployment automation.
