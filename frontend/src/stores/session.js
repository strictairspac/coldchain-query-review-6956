import{api}from'../api/client.js';
export const session={get:()=>JSON.parse(localStorage.getItem('qr-session')||'null'),set:data=>localStorage.setItem('qr-session',JSON.stringify(data)),clear:()=>localStorage.removeItem('qr-session'),async refresh(){const current=this.get();if(!current)return null;const me=await api('/auth/me');const data={...current,...me};this.set(data);return data}};
