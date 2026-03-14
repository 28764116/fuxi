export default {
  common: {
    entity: 'Entity',
    relation: 'Relation',
    processing: 'Processing',
    completed: 'Completed',
    failed: 'Failed',
    upload: 'Upload File',
    refresh: 'Refresh',
    submit: 'Submit',
    cancel: 'Cancel'
  },

  graph: {
    title: 'Real-time Knowledge Graph',
    entityTypes: 'Entity Types',
    emptyState: 'No graph data',
    emptyHint: 'Please upload a document or enter text content',
    processingState: 'Extracting entities...',
    processingHint: 'Graph will be generated soon',
    realtimeAnalysis: 'Real-time Analysis',
    edgeLabels: 'Edge Labels',
    nodeDetail: 'Node Details',
    edgeDetail: 'Relationship Details'
  },

  entityTypes: {
    person: 'Person',
    organization: 'Organization',
    location: 'Location',
    country: 'Country',
    concept: 'Concept',
    event: 'Event',
    product: 'Product',
    policy: 'Policy',
    time: 'Time',
    technology: 'Technology',
    military: 'Military',
    currency: 'Currency',
    law: 'Law',
    agreement: 'Agreement',
    industry: 'Industry',
    financial_product: 'Financial Product',
    facility: 'Facility',
    infrastructure: 'Infrastructure'
  },


  progress: {
    uploading: 'Uploading file',
    parsing: 'Parsing document',
    chunking: 'Smart segmentation',
    extracting: 'Extracting entities and relations',
    analyzing: 'AI analyzing text',
    building: 'Building graph',
    completing: 'Almost done',
    success: 'Processing completed',
    processingBlock: 'Processing block {current}/{total}',
    extracted: 'Extracted {count} triplets'
  },

  input: {
    placeholder: 'Enter text or paste content, press Cmd/Ctrl + Enter to submit...',
    extractEntities: 'Extract Entities',
    tooShort: 'Content too short, at least 10 characters required',
    invalidContent: 'Please enter meaningful text content'
  },

  toast: {
    uploadSuccess: 'Document uploaded successfully, processing',
    processSuccess: 'Processing completed: {entities} entities, {relations} relations',
    processFailed: 'Processing failed',
    noNewEntities: 'No new entities extracted',
    graphRefreshed: 'Graph refreshed',
    graphUpToDate: 'Graph is up to date',
    backendError: 'Cannot connect to backend, please ensure backend service is running'
  }
}
