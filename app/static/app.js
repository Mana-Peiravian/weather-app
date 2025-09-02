const $ = (sel) => document.querySelector(sel);
const api = (path, opts={}) => fetch(path, opts).then(r=>{ if(!r.ok) throw new Error(r.statusText); return r.json();});

const WMO = {
  0: "☀️ Clear",1:"🌤️ Mainly clear",2:"⛅ Partly cloudy",3:"☁️ Overcast",45:"🌫️ Fog",48:"🌫️ Rime fog",
  51:"🌦️ Drizzle",53:"🌦️ Drizzle",55:"🌧️ Drizzle",61:"🌦️ Rain",63:"🌧️ Rain",65:"🌧️ Rain",
  71:"🌨️ Snow",73:"🌨️ Snow",75:"❄️ Snow",80:"🌦️ Showers",81:"🌧️ Showers",82:"⛈️ Showers",
  95:"⛈️ Thunderstorm",96:"⛈️ TS hail",99:"⛈️ TS heavy hail"
};

const renderCurrent = (data) => {
  const c = data.current;
  const code = c.weather_code;
  return `
  <div class="tile">
    <div class="row"><span class="badge">Now</span><span>${new Date(c.time).toLocaleString()}</span></div>
    <div class="row"><div>${WMO[code]||code}</div></div>
    <div class="row small">Temp: <b>${c.temperature_2m}°C</b> • RH: ${c.relative_humidity_2m}% • Wind: ${c.wind_speed_10m} km/h</div>
  </div>`;
}

const renderForecast = (data) => {
  const d = data.daily; const tiles = [];
  for (let i=0;i<d.time.length;i++){
    const date = d.time[i];
    const code = d.weather_code[i];
    const rain = d.precipitation_sum[i];
    tiles.push(`
      <div class="tile">
        <div class="row"><span class="badge">${new Date(date).toDateString().slice(0,10)}</span></div>
        <div>${WMO[code]||code}</div>
        <div class="small">Max: <b>${d.temperature_2m_max[i]}°C</b> • Min: ${d.temperature_2m_min[i]}°C</div>
        <div class="small">Precip: ${rain} mm</div>
        <div class="small">Sunrise: ${new Date(d.sunrise[i]).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})} • Sunset: ${new Date(d.sunset[i]).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}</div>
      </div>
    `);
  }
  return tiles.join("\n");
}

// Search handlers
$("#searchForm").addEventListener("submit", async (e)=>{
  e.preventDefault();
  const q = $("#q").value.trim(); if(!q) return;
  try{
    const loc = await api(`/api/resolve_location?q=${encodeURIComponent(q)}`);
    const cur = await api(`/api/weather/current?lat=${loc.lat}&lon=${loc.lon}`);
    const fc = await api(`/api/weather/forecast?lat=${loc.lat}&lon=${loc.lon}&days=5`);
    $("#current").innerHTML = renderCurrent(cur);
    $("#forecast").innerHTML = renderForecast(fc);
  }catch(err){ alert("Search failed: "+err.message); }
});

$("#useGps").addEventListener("click", ()=>{
  if(!navigator.geolocation){ alert("Geolocation not supported"); return; }
  navigator.geolocation.getCurrentPosition(async (pos)=>{
    const {latitude, longitude} = pos.coords;
    try{
      const cur = await api(`/api/weather/current?lat=${latitude}&lon=${longitude}`);
      const fc = await api(`/api/weather/forecast?lat=${latitude}&lon=${longitude}&days=5`);
      $("#current").innerHTML = renderCurrent(cur);
      $("#forecast").innerHTML = renderForecast(fc);
    }catch(err){ alert("GPS fetch failed: "+err.message); }
  }, (err)=> alert(err.message), {enableHighAccuracy:true, timeout:10000});
});

// CRUD handlers
async function refreshList(){
  const rows = await api('/api/queries');
  const html = rows.map(r=>{
    const maps = `https://www.google.com/maps?q=${r.lat},${r.lon}`;
    const yt = `https://www.youtube.com/results?search_query=${encodeURIComponent(r.resolved_name+' travel vlog')}`;
    return `<div class="tile">
      <div class="row"><b>${r.resolved_name}, ${r.country||''}</b> <span class="small">(${r.date_from} → ${r.date_to})</span></div>
      <div class="row small"><a class="link" href="${maps}" target="_blank">Map</a> · <a class="link" href="${yt}" target="_blank">YouTube</a> · <a class="link" href="/api/export?qid=${r.id}&format=json" target="_blank">JSON</a> · <a class="link" href="/api/export?qid=${r.id}&format=csv" target="_blank">CSV</a> · <a class="link" href="/api/export?qid=${r.id}&format=md" target="_blank">MD</a></div>
      <div class="row">
        <button class="btn" onclick="view(${r.id})">Read</button>
        <button class="btn" onclick="editRec(${r.id})">Update</button>
        <button class="btn" onclick="del(${r.id})">Delete</button>
      </div>
    </div>`
  }).join("\n");
  $("#list").innerHTML = html || '<div class="small">No records yet.</div>';
}

window.view = async (id)=>{
  const rec = await api(`/api/queries/${id}`);
  $("#current").innerHTML = `<div class="tile"><div class="row"><span class="badge">Saved</span><b>${rec.meta.resolved_name}</b> (${rec.meta.date_from} → ${rec.meta.date_to})</div></div>`;
  $("#forecast").innerHTML = renderForecast(rec.data);
}

window.editRec = async (id)=>{
  const loc = prompt('New location (leave blank to keep)');
  const df = prompt('New date_from (YYYY-MM-DD, blank to keep)');
  const dt = prompt('New date_to (YYYY-MM-DD, blank to keep)');
  const body = {};
  if(loc) body.location = loc;
  if(df) body.date_from = df;
  if(dt) body.date_to = dt;
  try{
    await api(`/api/queries/${id}`, {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
    await refreshList();
  }catch(err){ alert('Update failed: '+err.message); }
}

window.del = async (id)=>{
  if(!confirm('Delete this record?')) return;
  try{
    await api(`/api/queries/${id}`, {method:'DELETE'});
    await refreshList();
  }catch(err){ alert('Delete failed: '+err.message); }
}

$("#saveForm").addEventListener("submit", async (e)=>{
  e.preventDefault();
  const location = $("#saveLocation").value.trim();
  const date_from = $("#from").value;
  const date_to = $("#to").value;
  if(!location || !date_from || !date_to){ alert('Please fill all fields'); return; }
  try{
    await api('/api/queries', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({location, date_from, date_to})});
    $("#saveForm").reset();
    await refreshList();
  }catch(err){ alert('Create failed: '+err.message); }
});

$("#infoBtn").addEventListener('click', ()=>{
  window.open('https://www.linkedin.com/company/product-manager-accelerator/', '_blank');
});

refreshList();