import{api,put}from'./client.js';export const getAccess=()=>api('/access');export const putAccess=(userId,customers)=>put('/access/'+userId,{customers});
