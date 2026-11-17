import{session}from'./stores/session.js';import{ROLES}from'./constants/enums.js';import{routes,current}from'./router/routes.js';import{esc}from'./utils/html.js';import{loginPage}from'./pages/login.js';import{samplesPage}from'./pages/samples.js';import{reviewPage}from'./pages/review.js';import{historyPage}from'./pages/history.js';import{evidencePage}from'./pages/evidence.js';import{accessPage}from'./pages/access.js';import{api}from'./api/client.js';import{table}from'./components/common/table.js';
const pages={samples:samplesPage,review:reviewPage,history:historyPage,evidence:evidencePage,access:accessPage};
async function render(){let user=session.get();if(!user)return loginPage(render);const route=current();
  // 每次进入页面刷新一次授权范围，管理员刚改的授权立刻反映到导航与表单。
  try{user=await session.refresh()||user}catch(e){}
  document.querySelector('#app').innerHTML=`<div class="shell"><aside class="sidebar"><div class="eyebrow">CHENGGANG / 2026</div><div class="brand">澄港冷链<br>SQL 复核台</div><nav>${routes.map(([r,n,t])=>`<a href="#${r}" class="${route===r?'active':''}"><span class="mono">${n}</span>　${t}</a>`).join('')}${user.role==='admin'?'<a href="#access" class="'+(route==='access'?'active':'')+'">05　客户授权</a><a href="#audit" class="'+(route==='audit'?'active':'')+'">06　操作审计</a>':''}</nav><footer>温控结算 · 只读查询环境<br>PostgreSQL 16 / 600 条固定账单<br><br><span class="badge">${ROLES[user.role]}</span><br>可查客户：${(user.customers||[]).length?esc(user.customers.join('、')):'无'}<br><a href="#" id="logout">退出工作台 ↗</a></footer></aside><main class="workspace"><div class="topline"><span class="eyebrow">FINANCIAL QUERY / REVIEW DESK</span><span>${esc(user.email)} · ${ROLES[user.role]}</span></div><div id="page" class="bodyenter"></div></main></div>`;
  document.querySelector('#logout').onclick=e=>{e.preventDefault();session.clear();render()};const el=document.querySelector('#page');
  try{
    if(route==='audit'){const logs=await api('/audit');el.innerHTML='<h1>操作审计</h1>'+table(['时间','账号','动作'],logs.map(x=>[esc(x.created_at),esc(x.actor),esc(x.action)]))}
    else if(route==='access'&&user.role!=='admin')el.innerHTML='<h2>仅管理员可配置客户授权</h2>'
    else await(pages[route]||samplesPage)(el)
  }catch(e){el.innerHTML='<h2>暂时无法加载</h2><p class="error">'+esc(e.message)+'</p><button id="retry">重新加载</button>';el.querySelector('button').onclick=render}}
window.addEventListener('hashchange',render);render();