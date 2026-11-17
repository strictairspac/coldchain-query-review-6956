/** @typedef {{id:number,name:string,description:string,original_sql:string}} Sample */
/** @typedef {{id:number,name:string,sample_id:number,candidate_sql:string,status:string,status_reason:string,scope:string[],created_by:string}} Batch */
/** @typedef {{id:number,batch_id:number,result:Object,scope:string[],status_reason:string}} Evidence */
export const entityNames={sample:'SQL 样本',batch:'复核批次',evidence:'执行证据'};
