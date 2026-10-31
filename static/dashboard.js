'use strict';

const colors = ['#ffffff', '#ffffcc', '#ffefa5', '#fede80', '#febf5a', '#fd9e43', '#fd7034', '#f43d25', '#da141e', '#b60026', '#800026'];
const plotConfig = {displaylogo: false, showSendToCloud: false, showEditInChartStudio: false,
    modeBarButtonsToRemove: ['sendDataToCloud', 'editInChartStudio'], responsive: true};
const byId = id => document.getElementById(id);
let busy = false, stopped = false, paused = false, totals = {};

function localTime(date) {
    const pad = n => String(n).padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

async function api(url, options = {}) {
    const response = await fetch(url, {cache: 'no-store', ...options});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '无法读取统计。');
    return data;
}

async function control(action) {
    try {
        await api(`/control/${action}`, {method: 'POST', headers: {
            'X-KMCounter-Token': document.querySelector('meta[name="control-token"]').content}});
        if (action === 'stop') {
            stopped = true;
            byId('status').textContent = '程序已退出';
            byId('pause-button').disabled = true;
            byId('stop-button').disabled = true;
        } else await refresh();
    } catch (error) { byId('error').textContent = error.message; }
}

async function paintCounts() {
    const start = byId('start-datetime').value, end = byId('end-datetime').value;
    if (!start || !end || start > end) throw new Error('请选择有效的起止时间。');
    const [counts, rates] = await api('/fetch_key_counts', {method:'POST',
        headers: {'Content-Type':'application/json'}, body:JSON.stringify({start_time:start, end_time:end})});
    document.querySelectorAll('.key').forEach(node => {node.style.backgroundColor='white'; node.title='0 次';});
    ['Button.left','Button.middle','Button.right'].forEach(id => {
        byId(id).style.fill='#f0f0f0'; byId(id).querySelector('title').textContent='0 次';
    });
    let keyboard=0, mouse=0;
    const grid = Array.from({length:100}, () => Array(100).fill(0));
    for (const [key, count] of Object.entries(counts)) {
        const position = key.match(/_position_(\d+)_(\d+)$/);
        if (position) {
            const x=Number(position[1]), y=Number(position[2]);
            if (x<100 && y<100) grid[y][x]+=count;
            continue;
        }
        if (key.startsWith('Button.')) mouse+=count; else keyboard+=count;
        const element=byId(key);
        if (element) {
            const color=colors[Math.min(10, Math.floor((rates[key] || 0)*10))];
            if (key.startsWith('Button.')) {
                element.style.fill=color; element.querySelector('title').textContent=`${count} 次`;
            } else { element.style.backgroundColor=color; element.title=`${count} 次`; }
        }
    }
    byId('keyboard-total').textContent=keyboard.toLocaleString();
    byId('mouse-total').textContent=mouse.toLocaleString();
    const maximum=grid.reduce((max,row)=>Math.max(max,...row),0);
    const normalized=grid.map(row=>row.map(value=>maximum ? Math.log1p(value)/Math.log1p(maximum) : 0));
    await Plotly.react('heatmap', [{z:normalized, customdata:grid, type:'heatmap', zmin:0,zmax:1,
        colorscale: colors.map((color,i)=>[i/10,color]),hovertemplate:'%{customdata} 次<extra></extra>'}],
        {margin:{t:5,b:5,l:5,r:30},xaxis:{visible:false},yaxis:{visible:false,autorange:'reversed'}},
        {...plotConfig,displayModeBar:false});
}

async function refresh() {
    if (busy || stopped) return;
    busy=true;
    try {
        if (byId('live').checked) byId('end-datetime').value=localTime(new Date());
        const [state, history]=await Promise.all([api('/status'),api('/fetch_total_key_counts')]);
        paused=state.paused; totals=history;
        byId('status').textContent=state.errors.length ? '需要处理错误' : (paused ? '已暂停' : '正在统计');
        byId('pause-button').textContent=paused ? '继续统计' : '暂停统计';
        byId('error').textContent=state.errors.join('\n');
        await Plotly.react('plot',[{x:Object.keys(totals),y:Object.values(totals),type:'bar',width:60000,marker:{color:'#5285c6'}}],
            {margin:{t:20,b:50,l:55,r:10},xaxis:{type:'date',tickformat:'%m-%d %H:%M',title:{text:'时间'}},
                yaxis:{title:{text:'键盘与鼠标次数'}}},plotConfig);
        await paintCounts();
    } catch(error) {
        byId('status').textContent='连接或读取失败';
        byId('error').textContent=error.message;
    } finally {busy=false;}
}

document.addEventListener('DOMContentLoaded', () => {
    const today=new Date(); today.setHours(0,0,0,0);
    byId('start-datetime').value=localTime(today);
    byId('end-datetime').value=localTime(new Date());
    ['start-datetime','end-datetime'].forEach(id=>byId(id).addEventListener('change',()=>{byId('live').checked=false;}));
    byId('check-button').addEventListener('click',refresh);
    byId('live').addEventListener('change',refresh);
    byId('full-range').addEventListener('click',()=>{
        const first=Object.keys(totals).sort()[0];
        if (first) byId('start-datetime').value=first.replace(' ','T');
        byId('live').checked=true; refresh();
    });
    byId('pause-button').addEventListener('click',()=>control(paused?'resume':'pause'));
    byId('stop-button').addEventListener('click',()=>{
        if (confirm('退出后将停止统计。下次登录时仍会按开机启动设置运行。')) control('stop');
    });
    refresh(); setInterval(refresh,5000);
});
