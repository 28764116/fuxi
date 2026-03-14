export default {
  common: {
    entity: '实体',
    relation: '关系',
    processing: '处理中',
    completed: '完成',
    failed: '失败',
    upload: '上传文件',
    refresh: '刷新',
    submit: '提交',
    cancel: '取消'
  },

  graph: {
    title: '实时知识图谱',
    entityTypes: '实体类型',
    emptyState: '暂无图谱数据',
    emptyHint: '请先上传文档或输入文本内容',
    processingState: '正在提取实体...',
    processingHint: '图谱即将生成',
    realtimeAnalysis: '实时分析中',
    edgeLabels: '边标签',
    nodeDetail: '节点详情',
    edgeDetail: '关系详情'
  },

  entityTypes: {
    person: '人物',
    organization: '组织',
    location: '地点',
    country: '国家',
    concept: '概念',
    event: '事件',
    product: '产品',
    policy: '政策',
    time: '时间',
    technology: '技术',
    military: '军事',
    currency: '货币',
    law: '法律',
    agreement: '协议',
    industry: '行业',
    financial_product: '金融产品',
    facility: '设施',
    infrastructure: '基础设施'
  },


  progress: {
    uploading: '正在上传文件',
    parsing: '正在解析文档',
    chunking: '正在智能分段',
    extracting: '正在提取实体和关系',
    analyzing: 'AI 正在分析文本',
    building: '正在构建图谱',
    completing: '即将完成',
    success: '处理完成',
    processingBlock: '处理块 {current}/{total}',
    extracted: '提取 {count} 个三元组'
  },

  input: {
    placeholder: '输入文本或粘贴内容，按 Cmd/Ctrl + Enter 提交...',
    extractEntities: '提取实体',
    tooShort: '内容太短，至少需要10个字符',
    invalidContent: '请输入有意义的文本内容'
  },

  toast: {
    uploadSuccess: '文档上传成功，正在处理',
    processSuccess: '处理完成：{entities} 个实体，{relations} 个关系',
    processFailed: '处理失败',
    noNewEntities: '未提取到新实体',
    graphRefreshed: '图谱已刷新',
    graphUpToDate: '图谱已是最新状态',
    backendError: '无法连接到后端，请确保后端服务已启动'
  }
}
