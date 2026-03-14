// File 对象无法 JSON.stringify，使用模块级变量暂存
// 同一 SPA 内页面跳转不会丢失
let _pending: { isPending: boolean; files: File[]; simulationRequirement: string } = {
  isPending: false,
  files: [],
  simulationRequirement: ''
}

export const setPendingUpload = (files: File[], simulationRequirement: string) => {
  _pending = { isPending: true, files, simulationRequirement }
}

export const getPendingUpload = () => {
  return _pending
}

export const clearPendingUpload = () => {
  _pending = { isPending: false, files: [], simulationRequirement: '' }
}
