# NovaMart Multi-Agent Customer Support Architecture

## 1. Purpose

NovaMart is a production-oriented multi-agent customer support system built on
Amazon Bedrock and Amazon Bedrock AgentCore.

The system receives a customer request, determines which specialist agents are
required, coordinates shared state, retrieves grounded policy knowledge, applies
business rules, and produces a final customer-facing response.

The architecture is designed around:

- explicit agent responsibilities
- deterministic routing rules
- grounded retrieval
- shared workflow state
- optimistic concurrency control
- observability
- safety guardrails
- independently testable components
- reproducible AWS deployment

---

## 2. Core Agents

### OrchestratorAgent

Responsibilities:

- initialize or restore workflow state
- classify the request
- determine the required agent sequence
- coordinate specialist agents
- maintain routing history
- ensure CommunicationAgent runs last

The OrchestratorAgent must not compose the final customer-facing response.

### InventoryAgent

Responsibilities:

- retrieve customer profile information
- retrieve customer tier
- retrieve orders
- retrieve order status
- expose factual order/customer context

The InventoryAgent does not interpret policies or approve refunds.

### PolicyAgent

Responsibilities:

- interpret policy-related questions
- coordinate policy retrieval
- run specialized retrievers concurrently
- merge and deduplicate retrieved policy evidence
- synthesize grounded policy context

The PolicyAgent coordinates:

- ReturnsPolicyRetriever
- ShippingPolicyRetriever
- WarrantyPolicyRetriever

### RefundAgent

Responsibilities:

- evaluate return/refund requests using validated workflow context
- verify required order/customer facts are available
- determine eligibility
- prepare the refund decision/result

The RefundAgent must not invent missing order facts.

### CommunicationAgent

Responsibilities:

- read completed workflow context
- convert internal results into a clear customer-facing response
- maintain professional and empathetic tone
- avoid exposing internal agent reasoning or infrastructure details

CommunicationAgent is always the final agent in a completed request.

---

## 3. Routing Contract

### Rule 1 — Session Initialization

Every request starts by creating or restoring workflow state.

### Rule 2 — Order / Return / Refund Requests

Route:

Orchestrator
→ InventoryAgent
→ RefundAgent
→ CommunicationAgent

### Rule 3 — Policy Meaning Questions

Examples:

- "How long is the return window?"
- "What does the warranty cover?"
- "How much is express shipping?"

Route:

Orchestrator
→ PolicyAgent
→ CommunicationAgent

### Rule 4 — Customer / Account Questions

Examples:

- "What tier am I?"
- "What orders do I have?"
- "Has my order shipped?"

Route:

Orchestrator
→ InventoryAgent
→ CommunicationAgent

### Rule 5 — Pure Calculation Requests

Requests requiring no customer, order, refund, or policy data should not invoke
unnecessary specialist agents.

Route:

Orchestrator
→ CommunicationAgent

### Rule 6 — Final Response

Every successful request ends with CommunicationAgent.

The Orchestrator must never directly generate the customer-facing response.

---

## 4. Parallel Policy Retrieval

PolicyAgent fans out to three independent retrievers concurrently:

               PolicyAgent
                    |
        +-----------+-----------+
        |           |           |
     Returns     Shipping    Warranty
    Retriever    Retriever   Retriever
        |           |           |
     Bedrock      Bedrock     Bedrock
        KB          KB          KB
        +-----------+-----------+
                    |
             Merge / Deduplicate
                    |
              Policy Synthesis

Retrievers should fail independently.

If one retriever fails but relevant evidence is available from another source,
PolicyAgent may continue.

If no usable policy evidence is available, the workflow must return a controlled
failure rather than hallucinating policy information.

---

## 5. Shared Workflow State

Workflow state is persisted in DynamoDB.

Each workflow contains, at minimum:

- session_id
- customer_id
- original_query
- request_type
- status
- route_history
- inventory_context
- policy_context
- refund_context
- final_response
- version
- created_at
- updated_at

### Optimistic Locking

Every update includes an expected version.

A successful update increments the version.

Concurrent writes using a stale version must fail rather than silently overwrite
newer state.

---

## 6. State Ownership

Agents do not directly manipulate DynamoDB.

State persistence is handled through a dedicated state repository layer.

This separates:

- agent reasoning
- domain state
- AWS persistence

and makes unit testing possible without requiring AWS.

---

## 7. Tool Boundaries

Agents interact with external systems through explicit tools or service
interfaces.

Examples:

InventoryAgent:
- get_customer
- get_customer_tier
- get_order
- list_orders

Policy retrievers:
- retrieve_returns_policy
- retrieve_shipping_policy
- retrieve_warranty_policy

RefundAgent:
- get_workflow_context
- evaluate_refund
- initiate_refund

CommunicationAgent:
- get_completed_workflow

AWS SDK calls should be isolated from agent prompt logic wherever practical.

---

## 8. Configuration

Configuration is loaded from environment variables and typed application
settings.

Secrets must never be committed to Git.

`.env.example` contains only placeholders.

Expected runtime configuration includes:

- AWS region
- project name
- Knowledge Base IDs
- AgentCore Runtime ARN
- Guardrail ID/version
- observability configuration

AWS credentials are provided through the normal AWS credential chain, not
stored in project files.

---

## 9. Safety

The production deployment uses Amazon Bedrock Guardrails.

Controls include:

- harmful content filtering
- sensitive-data protection
- PII handling
- prohibited business-topic controls
- profanity filtering where appropriate

Guardrails should be applied consistently to model interactions rather than only
to the orchestrator.

---

## 10. Observability

Every request has a correlation/session identifier.

Observability must capture:

- request lifecycle
- orchestrator routing
- worker-agent execution
- tool calls
- Knowledge Base retrieval
- failures
- latency

AWS deployment uses:

- CloudWatch Logs
- AWS X-Ray / tracing

Logs should be structured and must avoid exposing sensitive customer data.

---

## 11. Error Handling

Failures are classified into:

- validation errors
- missing customer/order data
- policy retrieval failures
- concurrency conflicts
- model failures
- AWS service failures
- internal application failures

Transient AWS failures may be retried with bounded retries.

Permanent failures must return controlled results and must not trigger
unbounded retry loops.

---

## 12. Testing Strategy

### Unit Tests

Test:

- routing decisions
- state transitions
- optimistic locking
- policy result merging
- refund rules
- configuration validation
- error handling

AWS dependencies should be mocked or replaced with test doubles.

### Integration Tests

Test:

- DynamoDB repositories
- Bedrock Knowledge Base adapters
- AgentCore integration boundaries
- observability adapters

### End-to-End Tests

Validate complete flows such as:

1. order return/refund
2. premium customer policy question
3. order-status lookup
4. warranty policy question
5. pure calculation request
6. missing customer/order
7. partial policy-retriever failure

---

## 13. Deployment

The target AWS architecture includes:

- Amazon Bedrock foundation models
- Amazon Bedrock AgentCore Runtime
- AgentCore Memory
- Amazon Bedrock Guardrails
- Amazon Bedrock Knowledge Bases
- Amazon S3 / vector storage
- Amazon DynamoDB
- Amazon CloudWatch
- AWS X-Ray
- IAM

Infrastructure should be reproducible through Infrastructure as Code wherever
practical.

Manual console configuration should be minimized.

---

## 14. Improvements Over the Initial Capstone Implementation

The portfolio implementation improves the original learning project by adding:

- clean Python package boundaries
- typed configuration
- explicit domain/state models
- repository abstractions for AWS persistence
- stronger separation between agents and infrastructure
- isolated AWS adapters
- controlled error types
- structured observability
- retriever fault isolation
- stronger test layering
- reproducible infrastructure
- CI-ready project structure
- safer secret handling
- professional public documentation

---

## 15. Engineering Principle

The system should not add agents merely for architectural appearance.

Every agent must have a distinct responsibility, bounded context, and measurable
reason to exist.

The goal is a maintainable production-oriented system, not maximum agent count.
