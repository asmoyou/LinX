
export const translations = {
  zh: {
    systemName: "LinX | 灵枢",
    brand: "灵枢",
    nav: {
      dashboard: "仪表盘",
      workforce: "数字化劳动力",
      tasks: "任务流协同",
      knowledge: "企业知识库",
      memory: "共享记忆",
      settings: "系统设置"
    },
    header: {
      status: "系统状态",
      optimal: "运行良好",
      search: "搜索资源...",
      theme: {
        light: "日间模式",
        dark: "夜间模式",
        system: "跟随系统"
      }
    },
    dashboard: {
      title: "系统概览",
      subtitle: "您的数字化劳动力实时性能指标。",
      activeAgents: "活跃智能体",
      goalsCompleted: "已完成目标",
      throughput: "任务吞吐量",
      computeLoad: "算力负载",
      offline: "个离线",
      inProgress: "个进行中",
      successRate: "成功率",
      clusters: "个集群在线",
      distribution: "工作负载分布",
      recentEvents: "最近事件",
      events: {
        decomposed: "目标 \"市场研究\" 已分解。",
        completed: "智能体 Analyst-Prime 已完成任务。",
        maintenance: "系统维护计划已安排。",
        scaled: "存储集群已扩容至 5TB。"
      }
    },
    workforce: {
      title: "数字化劳动力",
      subtitle: "管理并部署您的 AI 智能体员工。",
      deploy: "部署新智能体",
      searchPlaceholder: "搜索名称或技能...",
      filter: "筛选",
      memoryUsage: "内存占用",
      viewLogs: "查看日志",
      modalTitle: "选择智能体模板",
      status: {
        idle: "空闲",
        working: "工作中",
        offline: "离线"
      }
    },
    tasks: {
      title: "自主任务编排",
      subtitle: "提供高层目标；让 LinX 处理分解与分配。",
      inputPlaceholder: "描述您的企业目标（例如：'制定一份财务数字化转型战略'）",
      execute: "执行",
      decomposing: "正在分解目标...",
      awaiting: "等待分配...",
      result: "结果",
      id: "编号"
    },
    knowledge: {
      title: "企业知识",
      subtitle: "所有公司智能的集中式矢量索引存储。",
      permissions: "权限控制",
      upload: "上传文档",
      nodes: "存储节点",
      contentTypes: "内容类型",
      searchPlaceholder: "搜索 45,203 份索引文档...",
      table: {
        name: "名称",
        type: "类型",
        size: "大小",
        modified: "最后修改",
        actions: "操作"
      }
    },
    memory: {
      title: "多层记忆系统",
      subtitle: "支持跨智能体协作的上下文感知引擎。",
      layers: {
        company: "公司",
        user: "用户",
        agent: "智能体"
      },
      searchPlaceholder: "在潜在语义空间中搜索...",
      activity: "潜在活动",
      isolation: "隔离级别：高",
      isolationDesc: "跨用户记忆泄露防护已开启。所有智能体严格限制在当前上下文范围内。",
      share: "共享至所有智能体"
    }
  },
  en: {
    systemName: "LinX",
    brand: "LinX",
    nav: {
      dashboard: "Dashboard",
      workforce: "Workforce",
      tasks: "Task Flows",
      knowledge: "Knowledge",
      memory: "Memory",
      settings: "Settings"
    },
    header: {
      status: "System Status",
      optimal: "Optimal",
      search: "Search resources...",
      theme: {
        light: "Light",
        dark: "Dark",
        system: "System"
      }
    },
    dashboard: {
      title: "System Overview",
      subtitle: "Real-time performance metrics for your digital workforce.",
      activeAgents: "Active Agents",
      goalsCompleted: "Goals Completed",
      throughput: "Task Throughput",
      computeLoad: "Compute Load",
      offline: "offline",
      inProgress: "in progress",
      successRate: "success rate",
      clusters: "clusters online",
      distribution: "Workload Distribution",
      recentEvents: "Recent Events",
      events: {
        decomposed: 'Goal "Market Study" decomposed.',
        completed: 'Agent Analyst-Prime completed task.',
        maintenance: 'System maintenance scheduled.',
        scaled: 'Memory cluster scaled to 5TB.'
      }
    },
    workforce: {
      title: "Digital Workforce",
      subtitle: "Manage and deploy your AI-powered employees.",
      deploy: "Deploy New Agent",
      searchPlaceholder: "Search by name or skill...",
      filter: "Filter",
      memoryUsage: "Memory Usage",
      viewLogs: "View Logs",
      modalTitle: "Select Agent Template",
      status: {
        idle: "IDLE",
        working: "WORKING",
        offline: "OFFLINE"
      }
    },
    tasks: {
      title: "Autonomous Orchestration",
      subtitle: "Provide objectives; let LinX handle breakdown and assignment.",
      inputPlaceholder: "Describe your goal (e.g., 'Develop a digital transformation strategy')",
      execute: "Execute",
      decomposing: "Decomposing...",
      awaiting: "Awaiting allocation...",
      result: "Result",
      id: "ID"
    },
    knowledge: {
      title: "Enterprise Knowledge",
      subtitle: "Centralized vector-indexed storage for company intelligence.",
      permissions: "Permissions",
      upload: "Upload Doc",
      nodes: "Storage Nodes",
      contentTypes: "Content Types",
      searchPlaceholder: "Search indexed documents...",
      table: {
        name: "Name",
        type: "Type",
        size: "Size",
        modified: "Last Modified",
        actions: "Actions"
      }
    },
    memory: {
      title: "Memory System",
      subtitle: "Contextual awareness engine enabling collaboration.",
      layers: {
        company: "COMPANY",
        user: "USER",
        agent: "AGENT"
      },
      searchPlaceholder: "Search latent space...",
      activity: "Latent Activity",
      isolation: "Isolation: High",
      isolationDesc: "Leakage prevention active. Agents sandboxed to current context.",
      share: "Share with all agents"
    }
  }
};

export type Language = 'zh' | 'en';
export type TranslationType = typeof translations.zh;
