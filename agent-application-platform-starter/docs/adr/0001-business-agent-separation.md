# ADR-0001：业务系统与 Agent Platform 分离

## Status

Accepted

## Context

多个业务产品需要复用同一套 Agent 执行与 Artifact 交付能力，但各自拥有不同的用户、会员、商品和交易规则。

## Decision Drivers

- 避免 Agent Platform 耦合具体会员模型
- 允许多个业务系统复用
- 明确数据事实源

## Considered Options

- 单体平台包含全部业务
- 共享数据库但模块分离
- 独立系统通过版本化契约连接

## Decision

Business Application 拥有用户、会员、商品、订单与商业计费；Agent Platform 拥有 WorkOrder、Workflow、Invocation、Artifact、Technical Usage 与 Delivery。两者使用 Service Authentication、ExecutionGrant、WorkOrder、UsageReport 和 DeliveryPackage 通信。

## Consequences

- 业务系统可独立演进
- 增加分布式通信与幂等要求
- 需要独立数据库

## Risks

- 契约漂移导致集成失败
- 业务前端可能绕过业务后端直连 Agent

## Migration Plan

- 先冻结 Work Contracts
- 建立参考业务应用
- 禁止跨库查询

## Validation

- 契约测试
- 跨系统幂等测试
- 数据所有权审查
