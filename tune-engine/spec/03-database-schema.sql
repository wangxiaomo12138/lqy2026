-- =============================================================================
-- Tune Engine 数据表（MySQL 8+ / PostgreSQL 通用风格，按需微调类型）
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. target_registry：可调优对象注册表
-- -----------------------------------------------------------------------------
CREATE TABLE target_registry (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    target_id       VARCHAR(64)  NOT NULL UNIQUE COMMENT '如 contract-parse',
    name            VARCHAR(128) NOT NULL,
    description     TEXT,
    type            VARCHAR(32)  NOT NULL COMMENT 'workflow|agent|skill|composite',
    entry_ref       VARCHAR(128) NOT NULL COMMENT '当前入口版本 wf_xxx@v3',
    config_json     JSON         NOT NULL COMMENT '完整 Tunable Target 配置',
    benchmark_suite_id VARCHAR(64) NOT NULL,
    evaluator_id    VARCHAR(64)  NOT NULL,
    enabled         TINYINT(1)   NOT NULL DEFAULT 1,
    version         INT          NOT NULL DEFAULT 1 COMMENT '配置版本号',
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_target_enabled (enabled),
    INDEX idx_target_type (type)
);

-- -----------------------------------------------------------------------------
-- 2. benchmark_suite：测试集
-- -----------------------------------------------------------------------------
CREATE TABLE benchmark_suite (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    suite_id        VARCHAR(64)  NOT NULL UNIQUE,
    name            VARCHAR(128) NOT NULL,
    description     TEXT,
    case_count      INT          NOT NULL DEFAULT 0,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE benchmark_case (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    suite_id        VARCHAR(64)  NOT NULL,
    case_id         VARCHAR(64)  NOT NULL,
    input_json      JSON         NOT NULL COMMENT '传给目标 Agent/工作流的输入',
    ground_truth_json JSON       NULL COMMENT '标准答案，供 evaluator 使用',
    weight          DECIMAL(5,2) NOT NULL DEFAULT 1.00,
    tags            JSON         NULL COMMENT '如 ["hard","scan"]',
    enabled         TINYINT(1)   NOT NULL DEFAULT 1,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_suite_case (suite_id, case_id),
    INDEX idx_suite_enabled (suite_id, enabled)
);

-- -----------------------------------------------------------------------------
-- 3. tune_session：一次调优会话
-- -----------------------------------------------------------------------------
CREATE TABLE tune_session (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    session_id      VARCHAR(64)  NOT NULL UNIQUE,
    target_id       VARCHAR(64)  NOT NULL,
    status          VARCHAR(32)  NOT NULL DEFAULT 'pending'
                    COMMENT 'pending|running|optimal|best_effort|failed|stopped',
    mode            VARCHAR(32)  NOT NULL DEFAULT 'full_auto'
                    COMMENT 'full_auto|evaluate_only|dry_run',

    -- 起始与当前版本
    start_entry_ref VARCHAR(128) NOT NULL,
    current_entry_ref VARCHAR(128) NOT NULL,
    best_entry_ref  VARCHAR(128) NULL,
    best_score      DECIMAL(8,4) NULL,
    best_metrics_json JSON       NULL,

    -- 配置快照（启动时冻结，避免中途 target 被改）
    success_criteria_json JSON   NOT NULL,
    constraints_json      JSON   NOT NULL,

    current_iter    INT          NOT NULL DEFAULT 0,
    max_iters       INT          NOT NULL DEFAULT 8,
    stop_reason     VARCHAR(64)  NULL
                    COMMENT 'target_met|max_iters|stagnation|budget_exceeded|manual_stop|error',

    criteria_met    TINYINT(1)   NOT NULL DEFAULT 0,
    total_cost_tokens BIGINT     NOT NULL DEFAULT 0,
    total_duration_ms BIGINT     NOT NULL DEFAULT 0,

    input_payload_json JSON      NULL,
    error_message   TEXT         NULL,
    created_by      VARCHAR(64)  NULL,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    finished_at     DATETIME     NULL,

    INDEX idx_session_target (target_id),
    INDEX idx_session_status (status),
    INDEX idx_session_created (created_at)
);

-- -----------------------------------------------------------------------------
-- 4. tune_iter：每轮迭代记录
-- -----------------------------------------------------------------------------
CREATE TABLE tune_iter (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    session_id      VARCHAR(64)  NOT NULL,
    iter_no         INT          NOT NULL,
    status          VARCHAR(32)  NOT NULL DEFAULT 'running'
                    COMMENT 'running|completed|failed|skipped',

    entry_ref       VARCHAR(128) NOT NULL COMMENT '本轮使用的配置版本',
    candidate_entry_ref VARCHAR(128) NULL COMMENT '本轮提出的候选版本',

    -- 评估结果
    score           DECIMAL(8,4) NULL,
    pass_rate       DECIMAL(8,4) NULL,
    metrics_json    JSON         NULL,
    eval_json       JSON         NULL COMMENT '完整评估详情 failures 等',

    -- 补丁
    diagnosis_json  JSON         NULL COMMENT '失败归因',
    patch_json      JSON         NULL COMMENT '本轮补丁内容',
    patch_type      VARCHAR(32)  NULL COMMENT 'workflow|skill|agent|mcp|api|planner',
    patch_applied   TINYINT(1)   NOT NULL DEFAULT 0,
    promoted        TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '是否晋升为新 current_entry_ref',

    shadow_compare_json JSON     NULL COMMENT 'baseline vs candidate 对比',
    cost_tokens     BIGINT       NOT NULL DEFAULT 0,
    duration_ms     BIGINT       NOT NULL DEFAULT 0,
    error_message   TEXT         NULL,
    started_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at     DATETIME     NULL,

    UNIQUE KEY uk_session_iter (session_id, iter_no),
    INDEX idx_iter_session (session_id)
);

-- -----------------------------------------------------------------------------
-- 5. tune_run：单条 benchmark case 的执行记录
-- -----------------------------------------------------------------------------
CREATE TABLE tune_run (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    run_id          VARCHAR(64)  NOT NULL UNIQUE,
    session_id      VARCHAR(64)  NOT NULL,
    iter_no         INT          NOT NULL,
    case_id         VARCHAR(64)  NOT NULL,
    entry_ref       VARCHAR(128) NOT NULL,

    status          VARCHAR(32)  NOT NULL COMMENT 'success|failed|timeout|error',
    input_json      JSON         NOT NULL,
    output_json     JSON         NULL,
    trace_json      JSON         NULL COMMENT '5步规划轨迹 plan_trace',
    summary_text    TEXT         NULL COMMENT '模型总结输出',

    eval_score      DECIMAL(8,4) NULL,
    eval_passed     TINYINT(1)   NULL,
    eval_detail_json JSON        NULL,

    latency_ms      INT          NULL,
    cost_tokens     INT          NULL,
    error_message   TEXT         NULL,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_run_session_iter (session_id, iter_no),
    INDEX idx_run_case (case_id)
);

-- -----------------------------------------------------------------------------
-- 6. config_version：组件版本库（workflow/agent/skill 快照）
-- -----------------------------------------------------------------------------
CREATE TABLE config_version (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    ref             VARCHAR(128) NOT NULL UNIQUE COMMENT 'wf_contract_parse@v5',
    component_type  VARCHAR(32)  NOT NULL COMMENT 'workflow|agent|skill|mcp|api|master_agent',
    component_id    VARCHAR(64)  NOT NULL,
    version_no      INT          NOT NULL,
    config_json     JSON         NOT NULL COMMENT '完整配置快照',
    parent_ref      VARCHAR(128) NULL COMMENT '从哪个版本 patch 而来',
    patch_json      JSON         NULL COMMENT '相对 parent 的变更',
    created_by      VARCHAR(64)  NULL COMMENT 'tune_engine|manual',
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_component (component_type, component_id),
    INDEX idx_parent (parent_ref)
);

-- -----------------------------------------------------------------------------
-- 7. evaluator_registry：评估器注册（可选）
-- -----------------------------------------------------------------------------
CREATE TABLE evaluator_registry (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    evaluator_id    VARCHAR(64)  NOT NULL UNIQUE,
    name            VARCHAR(128) NOT NULL,
    type            VARCHAR(32)  NOT NULL COMMENT 'rule|json_diff|llm_judge|composite',
    config_json     JSON         NOT NULL,
    enabled         TINYINT(1)   NOT NULL DEFAULT 1,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
);
