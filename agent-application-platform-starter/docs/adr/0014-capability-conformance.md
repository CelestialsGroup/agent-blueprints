# ADR-0014：Capability Definition 与 Conformance

## Status

Accepted

## Context

仅使用同名字符串不能证明不同 Provider 可以安全替换。

## Decision Drivers

- 真正可替换
- 稳定 Scenario
- Provider 质量

## Considered Options

- 字符串 Capability
- 每个 Scenario 绑定实现
- 版本化 CapabilityDefinition + Conformance

## Decision

CapabilityDefinition 固定请求、结果、错误、副作用、取消、超时与 Artifact 语义。Plugin 只声明 implements。ProviderInstance 通过 Conformance Suite 后才能 healthy。

## Consequences

- 可验证替换
- 维护测试套件成本
- 重大语义变化需要 Major 版本

## Risks

- Conformance 覆盖不足
- Provider 宣称错误版本范围

## Migration Plan

- 先为 html.generate 和 html-to-pptx 建立套件
- 逐步扩展

## Validation

- Schema 测试
- 行为测试
- 跨 Provider 互换测试
