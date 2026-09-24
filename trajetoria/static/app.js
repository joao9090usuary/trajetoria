
"use strict";
const $ = id => document.getElementById(id);
const fmt = (x, n=2) => Number(x).toLocaleString("pt-BR", {minimumFractionDigits:n, maximumFractionDigits:n});
const defaults = {dry_mass:.35, propellant_mass:.08, thrust:12, burn_time:2, diameter:.05, drag_coefficient:.55, elevation:85, azimuth:30, wind_east:2, wind_north:.5, air_density:1.225, time_step:.02, max_time:120, motor_mode:"constant", thrust_curve:[], recovery_enabled:false, recovery_trigger:"apogee", recovery_delay:0, recovery_inflation:1, recovery_area:0.3, recovery_cd:1.5, recovery_altitude:50, recovery_time:5};
let motorCurve = [], importedMotors = [];
const configField = key => $("config-form").elements.namedItem(key) || $(key.replace(/_/g, "-"));
const fieldGroups = [
  ["Veículo", [["dry_mass","Massa seca","kg",.01,100],["propellant_mass","Propelente","kg",.001,100],["diameter","Diâmetro","m",.01,1],["drag_coefficient","Coef. de arrasto","Cd",0,2]]],
  ["Condições iniciais", [["elevation","Elevação","°",60,90],["azimuth","Azimute","°",0,360]]],
  ["Atmosfera", [["wind_east","Vento leste","m/s",-30,30],["wind_north","Vento norte","m/s",-30,30],["air_density","Densidade","kg/m³",0,1.5]]],
  ["Numérico", [["time_step","Passo máximo","s",.001,.1],["max_time","Limite de tempo","s",10,1000]]]
];
$("parameter-fields").innerHTML = fieldGroups.map(([title, fields], i) => {
  const grid = '<div class="field-grid">' + fields.map(([key,label,unit,min,max]) =>
    '<label'+(fields.length===3 && key==="air_density"?' class="full"':'')+'>'+label+'<span class="input-group"><input name="'+key+'" type="number" min="'+min+'" max="'+max+'" step="any" value="'+defaults[key]+'" required><em>'+unit+'</em></span></label>').join("") + '</div>';
  return i===3 ? '<details><summary>'+title+' <span>+</span></summary>'+grid+'</details>' :
    '<fieldset><legend>'+title+'</legend>'+grid+(i===1?'<p class="help-text">Elevação a partir do horizonte. Azimute a partir do norte, sentido horário.</p>':'')+'</fieldset>';
}).join("");
let study=null, observations=null, validation=null, convergence=null, studyNumber=0;
let playing=false, currentTime=0, frameTime=0, currentView="laboratorio", revision=0;
const camera = {yaw:-.9, pitch:.32, zoom:1};

/* ═══ Navigation ═══ */
function showView(name) {
  const views = ["laboratorio","calculos","validacao","sobre"];
  if (!views.includes(name)) name="laboratorio";
  currentView=name;
  document.querySelectorAll(".view").forEach(el=>el.classList.toggle("active",el.id==="view-"+name));
  document.querySelectorAll(".nav-link").forEach(el=>{el.classList.toggle("active",el.dataset.view===name);el.setAttribute("aria-current",el.dataset.view===name?"page":"false");});
  // Close mobile menu
  $("main-nav").classList.remove("open");
  $("menu-toggle").setAttribute("aria-expanded","false");
  if (name!=="laboratorio") setPlaying(false);
  requestAnimationFrame(drawAll);
}
document.querySelectorAll("[data-view]").forEach(el=>el.addEventListener("click",()=>{location.hash=el.dataset.view;}));
window.addEventListener("hashchange",()=>showView(location.hash.slice(1)));
showView(location.hash.slice(1)||"laboratorio");

/* Mobile menu toggle */
$("menu-toggle").addEventListener("click",()=>{
  const nav=$("main-nav");
  const open=!nav.classList.contains("open");
  nav.classList.toggle("open",open);
  $("menu-toggle").setAttribute("aria-expanded", open?"true":"false");
});

function message(text, error=false) {$("message").hidden=!text;$("message").textContent=text;$("message").classList.toggle("error",error);}

/* ═══ Config read/write ═══ */
function readConfig() {
  const c = {};
  for (const key of Object.keys(defaults)) {
    if (key === "thrust_curve") {
      c[key] = $("motor-mode").value === "curve" ? motorCurve : [];
    } else if (key === "recovery_enabled") {
      c[key] = $("recovery-enabled").checked;
    } else if (key === "motor_mode" || key === "recovery_trigger") {
      c[key] = $(key.replace("_", "-")).value;
    } else {
      const el = configField(key);
      c[key] = el ? Number(el.value) : defaults[key];
    }
  }
  return c;
}
function fillConfig(config) {
  Object.entries(config).forEach(([key,value])=>{
    if (key === "thrust_curve") {
      motorCurve = value.map(p=>[...p]);
    } else if (key === "recovery_enabled") {
      $("recovery-enabled").checked = value;
    } else if (key === "motor_mode" || key === "recovery_trigger") {
      $(key.replace("_", "-")).value = value;
    } else {
      const el = configField(key);
      if (el) el.value = value;
    }
  });
  updateFormVisibility();
  markDirty();
}
function updateFormVisibility() {
  const mm = $("motor-mode").value;
  $("constant-motor-fields").hidden = mm !== "constant";
  $("curve-motor-fields").hidden = mm !== "curve";
  const re = $("recovery-enabled").checked;
  $("recovery-fields").hidden = !re;
  const rt = $("recovery-trigger").value;
  $("recovery-time-label").hidden = rt !== "time";
  $("recovery-altitude-label").hidden = rt !== "altitude";
  document.querySelectorAll("#constant-motor-fields input").forEach(el=>el.disabled=mm!=="constant");
  document.querySelectorAll("#recovery-fields input, #recovery-fields select").forEach(el=>el.disabled=!re);
  drawMotor();
}
$("motor-mode").addEventListener("change", updateFormVisibility);
$("recovery-enabled").addEventListener("change", updateFormVisibility);
$("recovery-trigger").addEventListener("change", updateFormVisibility);

function markDirty() {
  const current=readConfig();
  const same=study && Object.keys(defaults).every(k=>JSON.stringify(current[k])===JSON.stringify(study.config[k]));
  $("config-status").textContent=same?"Resultados atualizados":"Alterações pendentes · execute a simulação";
}
$("config-form").addEventListener("input",()=>{$("preset").value="custom";markDirty();});
$("preset").addEventListener("change",()=>{
  if ($("preset").value==="custom") return;
  const c={...defaults};
  if ($("preset").value==="vacuum") Object.assign(c,{air_density:0,elevation:90,wind_east:0,wind_north:0});
  if ($("preset").value==="wind") Object.assign(c,{wind_east:8,wind_north:-4,elevation:80});
  fillConfig(c);
});

/* ═══ API ═══ */
async function api(path,payload) {
  const response=await fetch("/api/"+path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
  const data=await response.json();
  if (!response.ok) throw new Error(data.error||"Erro no cálculo.");
  return data;
}
function setPlaying(value) {
  playing=value;frameTime=0;$("play").textContent=value?"⏸":"▶";
  $("play").setAttribute("aria-label",value?"Pausar":"Reproduzir");
}
function resetValidation() {
  validation=null;$("validation-empty").hidden=false;$("validation-content").hidden=true;$("export-validation").disabled=true;
}

/* ═══ Simulation ═══ */
async function runSimulation(event) {
  if(event) event.preventDefault();
  if(!$("config-form").reportValidity()) return;
  const config=readConfig(), preset=$("preset").value;
  $("run").disabled=true;$("run").textContent="Calculando…";setPlaying(false);message("");
  try {
    const data=await api("simulate",config);
    study={...data,created_at:new Date().toISOString()};revision++;studyNumber++;
    $("study-name").textContent="Estudo "+String(studyNumber).padStart(3,"0");
    $("scenario-label").textContent=preset==="standard"?"Suborbital":preset==="vacuum"?"Vácuo":preset==="wind"?"Vento lateral":"Personalizado";
    $("engine-status").textContent="C++17 · ATIVO";
    const summary=study.summary;
    for (const [id,key,unit] of [["apogee","apogee","m"],["speed","max_speed","m/s"],["time","duration","s"],["distance","horizontal_distance","m"]]) {
      $("metric-"+id).innerHTML=fmt(summary[key],1)+' <small>'+unit+'</small>';
    }
    $("duration-label").textContent=study.status==="landed"?"Até contato com o solo":study.status==="time_limit"?"Limite atingido":"Sem decolagem";
    $("end-time").textContent=fmt(summary.duration)+" s";
    const top=study.events.find(e=>e.name==="apogee");
    currentTime=top?top.time:summary.duration/2;
    convergence=null;$("convergence-result").textContent="Execute para ver os valores.";
    resetValidation();$("validate").disabled=!observations;
    renderEvents();markDirty();updateTime();drawAll();
    if(study.status==="no_liftoff") message("Sem decolagem: empuxo insuficiente.",true);
    if(study.status==="time_limit") message("Limite de tempo atingido. Aumente o limite.");
  } catch(error) {message(error.message,true);}
  finally {$("run").disabled=false;$("run").textContent='Executar simulação';}
}
$("config-form").addEventListener("submit",runSimulation);

/* ═══ Time / Playback ═══ */
function indexAt(time) {
  if(!study) return 0;
  const samples=study.samples;
  let lo=0,hi=samples.length-1;
  while(lo<hi) {const mid=(lo+hi)>>1;if(samples[mid].time<time)lo=mid+1;else hi=mid;}
  return lo>0 && samples[lo].time>time ? lo-1 : lo;
}
function updateTime() {
  if(!study) return;
  const s=study.samples[indexAt(currentTime)];
  const ratio=study.summary.duration?currentTime/study.summary.duration*1000:0;
  $("timeline").value=ratio;$("inspection-slider").value=ratio;
  $("play-time").textContent="T+ "+fmt(currentTime)+" s";
  $("live-altitude").innerHTML=fmt(s.altitude,1)+' <small>m</small>';
  $("inspection-time").textContent="T+ "+fmt(s.time,3)+" s";
  const recoveryNames={None:"Desativado",Stowed:"Recolhido",Armed:"Aguardando ejeção",Inflating:"Em abertura",FullyOpen:"Aberto"};
  $("live-phase").textContent=s.state_motion === "Landed" ? "CONTATO COM O SOLO" : s.state_motion === "Supported" ? "APOIADO" : s.state_recovery === "Inflating" || s.state_recovery === "FullyOpen" ? "PARAQUEDAS: " + recoveryNames[s.state_recovery].toUpperCase() : s.state_motion === "Descending" ? "DESCIDA" : s.state_motor === "Burning" ? "VOO PROPULSADO" : "SUBIDA BALÍSTICA";
  const values=[["Altitude",s.altitude,"m"],["Velocidade",s.speed,"m/s"],["Massa",s.mass,"kg"],["Empuxo",s.thrust,"N"],["Densidade",s.density,"kg/m³"],["Vel. relativa",s.relative_speed,"m/s"],["Arrasto",s.drag,"N"],["Peso",s.weight,"N"],["|Aceleração|",s.acceleration,"m/s²"],["CdA efetivo",s.effective_cda + Math.PI*study.config.diameter**2/4 * study.config.drag_coefficient,"m²"]];
  $("instant-values").innerHTML=values.map(([label,v,unit])=>'<div><span>'+label+'</span><strong>'+fmt(v,label==="CdA efetivo"?6:3)+' '+unit+'</strong></div>').join("");
  for(const [label,value,unit] of [["Abertura",s.opening_fraction*100,"%"],["Arrasto do paraquedas",s.parachute_drag,"N"],["Aceleração vertical",s.acceleration_up,"m/s²"],["Variação da rapidez",s.along_velocity,"m/s²"],["Pressão dinâmica",s.dynamic_pressure,"Pa"]]) {
    const row=document.createElement("div"), name=document.createElement("span"), result=document.createElement("strong");
    name.textContent=label;result.textContent=fmt(value,3)+" "+unit;row.append(name,result);$("instant-values").append(row);
  }
}
for(const id of ["timeline","inspection-slider"]) $(id).addEventListener("input",()=>{
  if(!study)return;setPlaying(false);currentTime=Number($(id).value)/1000*study.summary.duration;updateTime();drawAll();
});
$("play").addEventListener("click",()=>{
  if(!study||!study.summary.duration)return;
  if(currentTime>=study.summary.duration || !playing && currentTime===0)currentTime=0;
  setPlaying(!playing);
});
const eventNames={liftoff:"Decolagem",burnout:"Fim de queima",apogee:"Apogeu",ground_contact:"Contato com o solo",recovery_trigger:"Gatilho de recuperação",ejection:"Ejeção",inflation_start:"Início da abertura",parachute_open:"Paraquedas aberto"};
function renderEvents() {
  $("events").innerHTML=study.events.map(e=>'<tr><td>'+eventNames[e.name]+'</td><td>'+fmt(e.time,6)+'</td><td>'+fmt(e.altitude,6)+'</td><td>'+(["apogee","ground_contact"].includes(e.name)?"Bisseção":"Fronteira")+'</td></tr>').join("")||'<tr><td colspan="4">Sem decolagem.</td></tr>';
}

/* ═══ Export / Import ═══ */
async function download(name,content,type="application/json") {
  try {
    const result=await api("export",{filename:name,content});
    const link=document.createElement("a");link.href=result.url;link.download=name;
    document.body.append(link);link.click();link.remove();
    message("Exportação salva: "+result.path);
  } catch(error) {message(error.message,true);}
}
function requireStudy() {if(study)return true;message("Execute uma simulação primeiro.",true);return false;}
$("export-json").addEventListener("click",()=>{if(requireStudy())download("trajetoria-estudo.json",JSON.stringify({...study,convergence,validation},null,2));});
$("save-config").addEventListener("click",()=>{if($("config-form").reportValidity())download("trajetoria-parametros.json",JSON.stringify(readConfig(),null,2));});
$("export-csv").addEventListener("click",()=>{
  if(!requireStudy())return;
  const keys=Object.keys(study.samples[0]);
  download("trajetoria-telemetria.csv",keys.join(",")+"\n"+study.samples.map(s=>keys.map(k=>s[k]).join(",")).join("\n"),"text/csv");
});
$("import-config").addEventListener("click",()=>$("config-file").click());
$("config-file").addEventListener("change",async event=>{
  const file=event.target.files[0];if(!file)return;
  try {
    if(file.size>2_000_000)throw new Error("Arquivo acima de 2 MB.");
    const imported=JSON.parse((await file.text()).replace(/^\uFEFF/,""));
    const c=imported.config||imported;
    if(!c||typeof c!=="object"||Array.isArray(c))throw new Error("JSON inválido.");
    const checked=await api("config",c);
    fillConfig(checked);$("preset").value="custom";message("Parâmetros importados e verificados.");
  } catch(error) {message(error.message,true);}
  event.target.value="";
});
$("import-motor").addEventListener("click", ()=>$("motor-file").click());
function selectMotor() {
  const motor=importedMotors[Number($("motor-select").value)];
  if(!motor)return;
  motorCurve=motor.thrust_curve.map(p=>[...p]);
  $("motor-mode").value="curve";
  $("motor-status").textContent=motor.name+" · "+motorCurve.length+" pontos verificados";
  const metadata=motor.metadata;
  $("motor-metadata").textContent=metadata.propellant_mass_kg ? "Propelente: "+fmt(metadata.propellant_mass_kg,4)+" kg. Motor carregado: "+fmt(metadata.loaded_motor_mass_kg,4)+" kg. As massas do veículo não são alteradas automaticamente." : "Defina as massas do veículo nos campos abaixo.";
  updateFormVisibility();markDirty();
}
$("motor-select").addEventListener("change",selectMotor);
$("motor-file").addEventListener("change", async event => {
  const file = event.target.files[0]; if(!file) return;
  try {
    if(file.size>2_000_000)throw new Error("Arquivo de motor acima de 2 MB.");
    const result=await api("motor-import",{filename:file.name,content:await file.text()});
    importedMotors=result.motors;
    const select=$("motor-select");select.replaceChildren();
    importedMotors.forEach((motor,i)=>{const option=document.createElement("option");option.value=i;option.textContent=motor.name;select.append(option);});
    select.hidden=$("motor-select-label").hidden=importedMotors.length<2;
    if(importedMotors.length>1) {
      const placeholder=document.createElement("option");placeholder.textContent="Selecione um motor";placeholder.value="";placeholder.disabled=true;placeholder.selected=true;select.prepend(placeholder);
      motorCurve=[];$("motor-status").textContent="Selecione um dos motores importados antes de simular.";drawMotor();markDirty();
    } else selectMotor();
  } catch (err) { message(err.message, true); }
  event.target.value = "";
});

/* ═══ Convergence ═══ */
$("convergence").addEventListener("click",async()=>{
  if(!requireStudy())return;
  const rev=revision;$("convergence").disabled=true;
  try{
    const data=await api("convergence",{config:study.config});
    if(rev!==revision)return;
    convergence=data;
    $("convergence-result").replaceChildren();
    data.steps.forEach((h,i)=>{const line=document.createElement("div");line.textContent="h = "+h+" s → "+fmt(data.apogees[i],8)+" m";$("convergence-result").append(line);});
    const line=document.createElement("div");line.textContent="Δ(h/2, h/4) = "+Math.abs(data.apogees[1]-data.apogees[2]).toExponential(4)+" m";$("convergence-result").append(line);
  } catch(error){message(error.message,true);} finally{$("convergence").disabled=false;}
});

/* ═══ Validation ═══ */
function parseObservations(text) {
  const lines=text.replace(/^\uFEFF/,"").trim().split(/\r?\n/);
  if(lines.length<3||lines.length>10001)throw new Error("CSV: 2 a 10.000 medições.");
  const split=line=>line.split(",").map(v=>v.trim().replace(/^"([^"]*)"$/,"$1"));
  const keys=split(lines[0]), allowed=["time","altitude","east","north","speed"];
  if(!keys.includes("time")||keys.length<2||new Set(keys).size!==keys.length||keys.some(k=>!allowed.includes(k)))throw new Error("Cabeçalho: time + altitude/east/north/speed.");
  let last=-1;
  return lines.slice(1).map((line,i)=>{
    const cells=split(line);
    if(cells.length!==keys.length||cells.some(v=>v===""||!Number.isFinite(Number(v))))throw new Error("Valores inválidos na linha "+(i+2));
    const row=Object.fromEntries(keys.map((key,k)=>[key,Number(cells[k])]));
    if(row.time<0||row.time<=last)throw new Error("Tempos devem ser crescentes.");
    last=row.time;return row;
  });
}
$("observations-file").addEventListener("change",async event=>{
  const file=event.target.files[0];if(!file)return;
  observations=null;$("validate").disabled=true;resetValidation();
  try{
    if(file.size>2_000_000)throw new Error("CSV acima de 2 MB.");
    observations=parseObservations(await file.text());
    $("observations-status").textContent=file.name+" · "+observations.length+" medições";
    $("validate").disabled=!study;message("");
  }catch(error){$("observations-status").textContent="Arquivo inválido.";message(error.message,true);}
  event.target.value="";
});
const uploadArea=document.querySelector(".upload-area");
if(uploadArea) uploadArea.addEventListener("keydown",event=>{if(event.key==="Enter"||event.key===" "){event.preventDefault();$("observations-file").click();}});
$("validate").addEventListener("click",async()=>{
  if(!requireStudy()||!observations)return;
  const rev=revision, rows=observations;$("validate").disabled=true;
  try {
    const result=await api("validate",{config:study.config,observations:rows});
    if(rev!==revision||rows!==observations)return;
    validation={...result,config:study.config,observations:rows,created_at:new Date().toISOString()};
    $("validation-empty").hidden=true;$("validation-content").hidden=false;$("export-validation").disabled=false;
    $("validation-table").innerHTML=Object.entries(result.metrics).map(([key,m])=>'<tr><td>'+key+' ('+m.unit+')</td><td>'+m.count+'</td><td>'+fmt(m.rmse,6)+'</td><td>'+fmt(m.mae,6)+'</td><td>'+fmt(m.bias,6)+'</td><td>'+fmt(m.max_abs,6)+'</td></tr>').join("");
    const first=Object.keys(result.metrics)[0];
    $("validation-note").textContent="Resíduos de "+first+" ("+result.metrics[first].unit+"). "+result.note;
    drawResiduals();message("Comparação concluída.");
  }catch(error){message(error.message,true);}finally{$("validate").disabled=!observations||!study;}
});
$("export-validation").addEventListener("click",()=>{if(validation)download("trajetoria-validacao.json",JSON.stringify(validation,null,2));});

/* ═══ 3D Scene ═══ */
function canvasContext(canvas) {
  const box=canvas.getBoundingClientRect();
  if(!box.width||!box.height)return null;
  const ratio=Math.min(devicePixelRatio||1,2);
  if(canvas.width!==Math.round(box.width*ratio)||canvas.height!==Math.round(box.height*ratio)){canvas.width=Math.round(box.width*ratio);canvas.height=Math.round(box.height*ratio);}
  const ctx=canvas.getContext("2d");ctx.setTransform(ratio,0,0,ratio,0,0);ctx.clearRect(0,0,box.width,box.height);
  return {ctx,w:box.width,h:box.height};
}
const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const normalize=a=>{const n=Math.hypot(...a)||1;return a.map(v=>v/n);};
function drawScene(){
  if(currentView!=="laboratorio")return;
  const surface=canvasContext($("scene"));if(!surface)return;
  const {ctx,w,h}=surface;
  if(!study){ctx.fillStyle="#5c6b7f";ctx.font="13px Inter";ctx.textAlign="center";ctx.fillText("Execute a simulação para visualizar",w/2,h/2);return;}
  const samples=study.samples, end=samples[samples.length-1], peak=study.summary.apogee;
  let xmin=0,xmax=0,ymin=0,ymax=0;
  for(const s of samples){xmin=Math.min(xmin,s.east);xmax=Math.max(xmax,s.east);ymin=Math.min(ymin,s.north);ymax=Math.max(ymax,s.north);}
  const span=Math.max(peak,xmax-xmin,ymax-ymin,15);
  const center=[(xmin+xmax)/2,(ymin+ymax)/2,peak*.43];
  const scale=Math.min(w*.85,h*.8)*camera.zoom;
  const cy=Math.cos(camera.yaw),sy=Math.sin(camera.yaw),cp=Math.cos(camera.pitch),sp=Math.sin(camera.pitch);
  function project(p){
    const x=(p[0]-center[0])/span,y=(p[1]-center[1])/span,z=(p[2]-center[2])/span;
    const horizontal=x*cy-y*sy, depth=x*sy+y*cy;
    const vertical=z*cp-depth*sp, distance=depth*cp+z*sp;
    const perspective=3/(3+distance);
    return [w*.56+horizontal*scale*perspective,h*.51-vertical*scale*perspective,distance];
  }
  function path(points,color,width=1,dash=[]){
    ctx.beginPath();points.forEach((p,i)=>{const q=project(p);if(i)ctx.lineTo(q[0],q[1]);else ctx.moveTo(q[0],q[1]);});
    ctx.strokeStyle=color;ctx.lineWidth=width;ctx.setLineDash(dash);ctx.stroke();ctx.setLineDash([]);
  }
  function label(p,text,color="#5c6b7f",dx=5,dy=-5){
    const q=project(p);ctx.font="9px JetBrains Mono, Consolas, monospace";ctx.fillStyle=color;ctx.textAlign="left";ctx.fillText(text,q[0]+dx,q[1]+dy);
  }
  const raw=span/5, magnitude=10**Math.floor(Math.log10(raw));
  const spacing=Math.ceil(raw/magnitude)*magnitude, radius=spacing*3;
  const gx=center[0],gy=center[1];
  for(let i=-3;i<=3;i++){
    path([[gx+i*spacing,gy-radius,0],[gx+i*spacing,gy+radius,0]],"#e8ebf0");
    path([[gx-radius,gy+i*spacing,0],[gx+radius,gy+i*spacing,0]],"#e8ebf0");
  }
  path([[0,0,0],[0,0,span*1.08]],"#a0aab8",1,[3,5]);
  for(let i=1;i<=5;i++) {const z=i*span/5;label([0,0,z],Math.round(z)+" m","#5c6b7f",-34,0);}
  path([[0,0,0],[span*.45,0,0]],"#8896a6");label([span*.45,0,0],"E / m");
  path([[0,0,0],[0,span*.45,0]],"#8896a6");label([0,span*.45,0],"N / m");
  const stride=Math.max(1,Math.floor(samples.length/600));
  const trail=samples.filter((_,i)=>i%stride===0);if(trail[trail.length-1]!==end)trail.push(end);
  path(trail.map(s=>[s.east,s.north,0]),"#c0c8d4",1,[2,6]);
  path(trail.map(s=>[s.east,s.north,s.altitude]),"#94a0b0",1.4,[4,4]);
  const upto=indexAt(currentTime),active=trail.filter(s=>s.time<=currentTime);
  const point=samples[upto];active.push(point);
  path(active.map(s=>[s.east,s.north,s.altitude]),"#1b4d8e",2.2);
  const top=study.events.find(e=>e.name==="apogee");
  if(top){const s=samples[indexAt(top.time)];path([[s.east,s.north,0],[s.east,s.north,s.altitude]],"#c8d0dc",1,[2,5]);label([s.east,s.north,s.altitude],"APOGEU  "+fmt(top.altitude,1)+" m","#1b4d8e",12,-12);}
  const origin=project([0,0,0]);ctx.beginPath();ctx.ellipse(origin[0],origin[1],8,3,0,0,Math.PI*2);ctx.strokeStyle="#5c6b7f";ctx.stroke();label([0,0,0],"ORIGEM","#5c6b7f",-22,18);
  if(study.status==="landed"){const q=project([end.east,end.north,0]);ctx.strokeStyle="#5c6b7f";ctx.beginPath();ctx.moveTo(q[0]-4,q[1]-4);ctx.lineTo(q[0]+4,q[1]+4);ctx.moveTo(q[0]+4,q[1]-4);ctx.lineTo(q[0]-4,q[1]+4);ctx.stroke();}
  let axis=point.speed>1?normalize([point.velocity_east,point.velocity_north,point.velocity_up]):[0,0,1];
  const u=normalize(cross(axis,Math.abs(axis[2])>.9?[0,1,0]:[0,0,1])),v=cross(axis,u);
  const length=span*.10,radiusRocket=length*.075;
  function world(x,y,z){return [point.east+u[0]*x+v[0]*y+axis[0]*z,point.north+u[1]*x+v[1]*y+axis[1]*z,point.altitude+u[2]*x+v[2]*y+axis[2]*z];}
  const faces=[];
  function face(points,color){const projected=points.map(p=>project(world(...p)));faces.push({points:projected,color,depth:projected.reduce((a,p)=>a+p[2],0)/projected.length});}
  for(let i=0;i<12;i++){
    const a=i*Math.PI/6,b=(i+1)*Math.PI/6,x1=Math.cos(a)*radiusRocket,y1=Math.sin(a)*radiusRocket,x2=Math.cos(b)*radiusRocket,y2=Math.sin(b)*radiusRocket;
    const light=Math.round(180+50*(Math.cos(a-.8)+1)/2);
    face([[x1,y1,-length*.38],[x2,y2,-length*.38],[x2,y2,length*.28],[x1,y1,length*.28]],"rgb("+light+","+(light+2)+","+(light+6)+")");
    face([[x1,y1,length*.28],[x2,y2,length*.28],[0,0,length*.62]],"#8896a6");
    face([[x1,y1,-length*.12],[x2,y2,-length*.12],[x2,y2,-length*.05],[x1,y1,-length*.05]],"#1b4d8e");
  }
  for(let i=0;i<4;i++){const a=i*Math.PI/2;face([[Math.cos(a)*radiusRocket,Math.sin(a)*radiusRocket,-length*.15],[Math.cos(a)*length*.22,Math.sin(a)*length*.22,-length*.44],[Math.cos(a)*radiusRocket,Math.sin(a)*radiusRocket,-length*.36]],"#6b7d94");}
  if(point.thrust>0&&point.speed>0.1)face([[radiusRocket*.8,0,-length*.38],[-radiusRocket*.8,0,-length*.38],[0,0,-length*.8]],"#a4b0c0");
  faces.sort((a,b)=>b.depth-a.depth).forEach(f=>{ctx.beginPath();f.points.forEach((q,i)=>i?ctx.lineTo(q[0],q[1]):ctx.moveTo(q[0],q[1]));ctx.closePath();ctx.fillStyle=f.color;ctx.fill();});
  const q=project([point.east,point.north,point.altitude]);ctx.beginPath();ctx.arc(q[0],q[1],3,0,Math.PI*2);ctx.fillStyle="#1b4d8e";ctx.fill();
  if(point.opening_fraction>0){
    const canopy=project([point.east,point.north,point.altitude+length*1.4]);
    const radius=Math.max(2,scale*.04*Math.sqrt(point.opening_fraction));
    ctx.strokeStyle="#536579";ctx.lineWidth=1;
    for(const dx of [-radius,0,radius]){ctx.beginPath();ctx.moveTo(q[0],q[1]);ctx.lineTo(canopy[0]+dx,canopy[1]);ctx.stroke();}
    ctx.beginPath();ctx.ellipse(canopy[0],canopy[1],radius,radius*.6,0,Math.PI,2*Math.PI);ctx.closePath();ctx.fillStyle="#e4e9ef";ctx.fill();ctx.stroke();
  }
  if(w>500){ctx.font="8px JetBrains Mono, monospace";ctx.fillStyle="#5c6b7f";ctx.textAlign="right";ctx.fillText("MALHA "+fmt(spacing,0)+" m",w-16,h-16);}
}

/* ═══ Charts ═══ */
function chart(canvas, series, timeLimit, cursor=null, allowNegative=false, color="#1b4d8e") {
  const surface=canvasContext(canvas);if(!surface)return;
  const {ctx,w,h}=surface,left=40,right=13,top=17,bottom=27,pw=w-left-right,ph=h-top-bottom;
  if(!series.length)return;
  let low=0,high=allowNegative?1e-6:1;
  for(const p of series){high=Math.max(high,p[1]);if(allowNegative)low=Math.min(low,p[1]);}
  if(allowNegative){const bound=Math.max(Math.abs(low),Math.abs(high),1e-6);low=-bound;high=bound;}else high*=1.1;
  const x=t=>left+t/Math.max(timeLimit,.01)*pw,y=v=>top+(high-v)/(high-low)*ph;
  ctx.font="9px JetBrains Mono, monospace";ctx.lineWidth=1;
  for(let i=0;i<=3;i++){
    const value=low+(high-low)*i/3,yy=y(value);
    ctx.strokeStyle="#edf0f4";ctx.beginPath();ctx.moveTo(left,yy);ctx.lineTo(w-right,yy);ctx.stroke();
    ctx.fillStyle="#5c6b7f";ctx.textAlign="right";ctx.fillText(fmt(value,Math.abs(value)<1?2:0),left-7,yy+3);
  }
  for(let i=0;i<=4;i++){ctx.fillStyle="#5c6b7f";ctx.textAlign="center";ctx.fillText(fmt(timeLimit*i/4,1),x(timeLimit*i/4),h-8);}
  const stride=Math.max(1,Math.floor(series.length/600)),points=series.filter((_,i)=>i%stride===0);if(points[points.length-1]!==series[series.length-1])points.push(series[series.length-1]);
  if(!allowNegative){
    const fill=ctx.createLinearGradient(0,top,0,h-bottom);fill.addColorStop(0,color+"20");fill.addColorStop(1,color+"02");
    ctx.beginPath();ctx.moveTo(x(points[0][0]),y(0));points.forEach(p=>ctx.lineTo(x(p[0]),y(p[1])));ctx.lineTo(x(points[points.length-1][0]),y(0));ctx.closePath();ctx.fillStyle=fill;ctx.fill();
  }
  ctx.beginPath();points.forEach((p,i)=>i?ctx.lineTo(x(p[0]),y(p[1])):ctx.moveTo(x(p[0]),y(p[1])));ctx.strokeStyle=color;ctx.lineWidth=1.8;ctx.stroke();
  if(cursor!==null){ctx.setLineDash([3,3]);ctx.strokeStyle="#a0aab8";ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(x(cursor),top);ctx.lineTo(x(cursor),h-bottom);ctx.stroke();ctx.setLineDash([]);}
}
function drawResiduals(){
  if(!validation||currentView!=="validacao")return;
  const key=Object.keys(validation.metrics)[0];
  chart($("residual-chart"),validation.residuals.filter(s=>s[key]).map(s=>[s.time,s[key].residual]),study.summary.duration,null,true,"#4a6fa5");
}
function drawAll(){
  drawMotor();
  drawScene();
  if(study&&currentView==="laboratorio"){
    chart($("altitude-chart"),study.samples.map(s=>[s.time,s.altitude]),study.summary.duration,currentTime);
    chart($("speed-chart"),study.samples.map(s=>[s.time,s.speed]),study.summary.duration,currentTime,false,"#2a6496");
    chart($("acceleration-chart"),study.samples.map(s=>[s.time,s.along_velocity]),study.summary.duration,currentTime,true,"#536579");
    chart($("drag-chart"),study.samples.map(s=>[s.time,s.drag]),study.summary.duration,currentTime,false,"#536579");
  }
  drawResiduals();
}

function drawMotor(){
  if(currentView!=="laboratorio")return;
  const c=readConfig(),curve=c.motor_mode==="curve"?c.thrust_curve:[[0,c.thrust],[c.burn_time,c.thrust]];
  if(!curve.length){canvasContext($("motor-curve-chart"));$("motor-summary").textContent="Importe e selecione uma curva para visualizar.";return;}
  let impulse=0;
  for(let i=1;i<curve.length;i++)impulse+=(curve[i][0]-curve[i-1][0])*(curve[i][1]+curve[i-1][1])/2;
  const duration=curve[curve.length-1][0];
  chart($("motor-curve-chart"),curve,duration);
  $("motor-summary").textContent="Impulso: "+fmt(impulse,3)+" N·s · duração: "+fmt(duration,3)+" s · pico: "+fmt(Math.max(...curve.map(p=>p[1])),2)+" N";
}
$("config-form").addEventListener("input",drawMotor);

/* ═══ Camera ═══ */
let drag=null;
$("scene").addEventListener("pointerdown",e=>{drag={x:e.clientX,y:e.clientY};$("scene").setPointerCapture(e.pointerId);});
$("scene").addEventListener("pointermove",e=>{if(!drag)return;camera.yaw+=(e.clientX-drag.x)*.008;camera.pitch=Math.max(-.1,Math.min(1.35,camera.pitch+(e.clientY-drag.y)*.006));drag={x:e.clientX,y:e.clientY};drawScene();});
$("scene").addEventListener("pointerup",()=>drag=null);
$("scene").addEventListener("pointercancel",()=>drag=null);
$("scene").addEventListener("wheel",e=>{e.preventDefault();camera.zoom=Math.max(.45,Math.min(2.5,camera.zoom*Math.exp(-e.deltaY*.001)));drawScene();},{passive:false});
$("scene").addEventListener("keydown",e=>{
  if(!["ArrowLeft","ArrowRight","ArrowUp","ArrowDown","+","-","="].includes(e.key))return;
  e.preventDefault();
  if(e.key==="ArrowLeft")camera.yaw-=.1;if(e.key==="ArrowRight")camera.yaw+=.1;
  if(e.key==="ArrowUp")camera.pitch=Math.min(1.35,camera.pitch+.08);if(e.key==="ArrowDown")camera.pitch=Math.max(-.1,camera.pitch-.08);
  if(e.key==="+"||e.key==="=")camera.zoom=Math.min(2.5,camera.zoom*1.1);if(e.key==="-")camera.zoom=Math.max(.45,camera.zoom/1.1);drawScene();
});
function cameraMode(side=false){Object.assign(camera,{yaw:side?-.7:-.9,pitch:side?0:.32,zoom:1});$("camera-orbit").classList.toggle("selected",!side);$("camera-side").classList.toggle("selected",side);drawScene();}
$("camera-orbit").addEventListener("click",()=>cameraMode());
$("camera-side").addEventListener("click",()=>cameraMode(true));
$("camera-reset").addEventListener("click",()=>cameraMode());
new ResizeObserver(()=>requestAnimationFrame(drawAll)).observe(document.querySelector(".results-column"));
window.addEventListener("resize",drawAll);

/* ═══ Animation ═══ */
function animate(now){
  if(playing&&study&&currentView==="laboratorio"){
    if(frameTime)currentTime=Math.min(study.summary.duration,currentTime+Math.min((now-frameTime)/1000,.1)*Number($("play-speed").value));
    updateTime();drawAll();
    if(currentTime>=study.summary.duration)setPlaying(false);
  }
  frameTime=now;requestAnimationFrame(animate);
}
requestAnimationFrame(animate);
runSimulation();
