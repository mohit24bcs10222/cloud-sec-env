# Environment Spec

**Purpose:** Details the spec for the desired initial environment and how we will measure the quality of the environment.

## Environment Characteristics

- Cloud security platform: specifically customer impacting flows:
    - Configure network policies (admin)
    - Access the internet, or something running on internal network (user)
    - Configure identity (admin)
- Log, metric, trace data, dashboards for common views of this data. High-value: GBs + of logs and traces per hour. Data is coherent (request ids in logs line up with those in traces, service names in logs line up w metrics) but messy (some incomplete telemetry / lack of request id wiring, fuzzy matched names).
- Ticketing system queryable using a tool contains change data, incident data.
- Infrastructure data over time, though not kubernetes. Multiple deployments of the same services, e.g. cloud-1, cloud-2, cloud-3 also shows up in the telemetry (such that investigation may sometimes need to be scoped). Example blog discussing some of the complexity is this.
- Messaging app access, with discussions coherent with the telemetry etc…
- Internal knowledge base access, with documents of varying quality (some out of date / incorrect info, some missing info).
- 10 tasks, including some of the following:
    - Deployment noise (many, many deployments at once and in different clouds which may or may not be the cause of the problem).
    - Red herrings (there are issues in multiple clouds but must scope to a particular environment).
    - Task input is an alert from a monitoring system (at least 7 of these).
    - Task input is a vague reference to an incident ticket (that has some more details, but still is vague / very user specific e.g. "customer X cannot access Y").

## Evaluating Environment Quality

| Area | How well we measure |
| --- | --- |
| coherence | Qualitative: someone will query the raw data and attempt to find inconsistencies. |
| difficulty | Lets take 2 models: Qwen3-8B and Opus. Qwen3-8B Pass@1 << Opus 4.6 Pass@1. Opus Pass@1 < 50%. As long as one of the good LLM models like Sonnet, Opus, Gpt5.4 could get trajectory right in a few passes it's good. |
| difficulty (subjective) | Qualitative: our experts will rate each task and solution as easy, medium, hard. |
| Complexity | Number of micro-services and clouds, number of calls etc. supported, length of trajectories. |
| realism | Qualitative: our experts will rate each task and solution as realistic, semi-realistic, or not realistic based on similarity to real cloud situations. |
