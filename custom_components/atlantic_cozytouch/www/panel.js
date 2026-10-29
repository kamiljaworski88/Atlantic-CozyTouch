/* Atlantic CozyTouch read-only dashboard; actual entity IDs audited 2026-10-29. */
const DATA = [
 ["🏠 Komfort", [["W domu","sensor.room_0_temperatura_pokojowa_strefa_1_2"],["Na zewnątrz","sensor.alfea_extensa_s_temperatura_zewnetrzna_2"],["Stan ogrzewania","sensor.room_0_stan_ogrzewania_id_153"],["Tryb","sensor.room_0_wykonywany_tryb_id_181"]]],
 ["♨️ Instalacja CO",[["Obieg moduł A","sensor.alfea_extensa_s_temperatura_obiegu_3"],["Obieg moduł B","sensor.alfea_extensa_s_temperatura_obiegu_4"],["Powrót","sensor.alfea_extensa_s_temperatura_powrotu_obiegu_id_116_2"],["TESC","sensor.tesc_0_default_temperatura_obiegu_2"],["Ciśnienie","sensor.alfea_extensa_s_cisnienie_wody_2"],["Aktywny obieg","sensor.alfea_extensa_s_aktywny_obieg_co_cwu_id_91_2"]]],
 ["🚿 CWU",[["Temperatura zasobnika","sensor.dhw_0_default_temperatura_cwu_2"],["Funkcja CWU","binary_sensor.dhw_0_default_stan_funkcji_cwu_id_99"],["Prąd dzisiaj (UTC)","sensor.energia_elektryczna_cwu_dzisiaj_utc"],["Prąd wczoraj (UTC)","sensor.energia_elektryczna_cwu_wczoraj_utc"]]],
 ["⚡ Energia CO i CWU",[["CO dzisiaj UTC","sensor.energia_elektryczna_co_dzisiaj_utc"],["CWU dzisiaj UTC","sensor.energia_elektryczna_cwu_dzisiaj_utc"],["CO wczoraj UTC","sensor.energia_elektryczna_co_wczoraj_utc"],["CWU wczoraj UTC","sensor.energia_elektryczna_cwu_wczoraj_utc"]]],
 ["📈 COP2 — eksperymentalny",[["CO","sensor.cop2_atlantic_co_eksperymentalny"],["CWU","sensor.cop2_atlantic_cwu_eksperymentalny"],["Łączny","sensor.cop2_atlantic_laczny_eksperymentalny"],["Jakość","sensor.cop2_atlantic_diagnostyka"]]],
 ["📉 COP1 — zaakceptowane próbki",[["Skumulowany CO","sensor.cop_atlantic_skumulowany_co_zaakceptowane_probki"],["Skumulowany CWU","sensor.cop_atlantic_skumulowany_cwu_zaakceptowane_probki"],["Ostatni CO","sensor.cop_atlantic_ostatni_zaakceptowany_co"],["Ostatni CWU","sensor.cop_atlantic_ostatni_zaakceptowany_cwu"],["Status obliczeń","sensor.cop_atlantic_status_obliczen"]]],
 ["⚙️ Sprężarka i pompy",[["Sprężarka pracuje","binary_sensor.alfea_extensa_s_sprezarka_pracuje_2"],["Modulacja","sensor.alfea_extensa_s_modulacja_sprezarki_2"],["Czas sprężarki","sensor.alfea_extensa_s_czas_pracy_sprezarki_godziny_2"],["Starty sprężarki","sensor.alfea_extensa_s_uruchomienia_sprezarki_2"],["Czas pompy CO","sensor.alfea_extensa_s_czas_pracy_pompy_co_2"],["Czas pompy CWU","sensor.alfea_extensa_s_czas_pracy_pompy_cwu_2"]]],
 ["🛡️ Diagnostyka",[["Chmura Atlantic","binary_sensor.odczyt_z_chmury_atlantic_dziala"],["Aktualność telemetrii","sensor.aktualnosc_telemetrii_atlantic"],["Ostatni odczyt","sensor.ostatni_udany_odczyt"],["Błąd generatora","sensor.alfea_extensa_s_blad_generatora_2"],["Kod jednostki zewnętrznej","sensor.alfea_extensa_s_kod_bledu_jednostki_zewnetrznej_2"],["Źródło ciepła","sensor.cop_atlantic_audyt_zrodel_ciepla"],["Gotowość COP","sensor.cop_atlantic_gotowosc_danych"],["Historia API","sensor.historia_energii_atlantic_test_api"],["Historia urządzenia","sensor.historia_energii_atlantic_odczyt_urzadzenia"]]],
 ["🔬 Surowe — niezweryfikowane",[["Przepływ ID112","sensor.alfea_extensa_s_odczyt_przeplywu_id_112_surowy_2"],["Grzałka CO1 (surowa)","sensor.alfea_extensa_s_moc_grzalki_wspomagajacej_co1_surowa"],["Grzałka CWU (surowa)","sensor.alfea_extensa_s_moc_grzalki_wspomagajacej_cwu_surowa"],["Hipoteza energii CO","sensor.alfea_extensa_s_hipoteza_energii_co_id_57_2"],["Hipoteza energii CWU","sensor.alfea_extensa_s_hipoteza_energii_cwu_id_59_2"]]]
];
const GRAPHS=[
 ["Temperatury domu · 24 h",["sensor.room_0_temperatura_pokojowa_strefa_1_2","sensor.alfea_extensa_s_temperatura_zewnetrzna_2"]],
 ["Obiegi CO · 24 h",["sensor.alfea_extensa_s_temperatura_obiegu_3","sensor.alfea_extensa_s_temperatura_obiegu_4","sensor.alfea_extensa_s_temperatura_powrotu_obiegu_id_116_2"]],
 ["CWU · 24 h",["sensor.dhw_0_default_temperatura_cwu_2"]]
];
const CSS=':host{display:block;font-family:var(--primary-font-family,Arial);background:var(--primary-background-color);color:var(--primary-text-color);min-height:100vh}*{box-sizing:border-box}main{max-width:1450px;margin:auto;padding:18px}h1{margin:2px 0;font-size:26px}h2{margin:0 0 12px;font-size:17px}p{color:var(--secondary-text-color);font-size:13px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr));gap:14px;margin-top:14px}.card{border:1px solid var(--divider-color);border-radius:15px;padding:17px;background:var(--card-background-color);min-width:0}.row{border-top:1px solid var(--divider-color);padding:10px 0;display:flex;align-items:center;justify-content:space-between;gap:12px;cursor:pointer}.row span{font-size:13px;color:var(--secondary-text-color);overflow-wrap:anywhere}.row b{font-size:14px;white-space:nowrap;text-align:right;font-variant-numeric:tabular-nums}.warning{border-left:4px solid var(--warning-color,#dd9b21);background:var(--secondary-background-color);padding:12px 14px;border-radius:6px;margin:16px 0;font-size:13px}.hero{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:18px 0}.hero .value{font-size:24px;font-weight:600}.small{opacity:.65;font-size:12px}.chart svg{width:100%;height:130px}.chart .legend{font-size:11px;color:var(--secondary-text-color);line-height:1.7}';
function el(tag,text,cls){const e=document.createElement(tag);if(text!==null&&text!==undefined)e.textContent=String(text);if(cls)e.className=cls;return e;}
function put(a,b){a.appendChild(b);return b;}
function display(s){if(!s||["unknown","unavailable","none"].includes(s.state))return "Brak danych";return s.state+(s.attributes.unit_of_measurement?" "+s.attributes.unit_of_measurement:"");}
class AtlanticCozytouchMonitor extends HTMLElement{
 constructor(){super();this.attachShadow({mode:"open"});this._hass=null;this._key="";this._sequence=0;}
 set hass(h){this._hass=h;if(!this.isConnected)return;const ids=DATA.flatMap(x=>x[1].map(y=>y[1]));const key=ids.map(id=>(h.states[id]||{}).state).join("|");if(key!==this._key){this._key=key;this.draw();}}
 connectedCallback(){this.draw();}
 disconnectedCallback(){this._sequence++;}
 detail(id){this.dispatchEvent(new CustomEvent("hass-more-info",{bubbles:true,composed:true,detail:{entityId:id}}));}
 row(label,id){const r=el("div",null,"row"),s=this._hass.states[id];r.tabIndex=0;r.setAttribute("role","button");put(r,el("span",label));put(r,el("b",display(s)));r.addEventListener("click",()=>this.detail(id));r.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();this.detail(id);}});return r;}
 draw(){
  if(!this._hass)return;
  const root=this.shadowRoot;root.replaceChildren();put(root,el("style",CSS));const main=put(root,el("main"));
  put(main,el("h1","PC Atlantic · Extensa S Duo XL 10"));put(main,el("p","Automatyczny monitoring read-only · rzeczywiste encje Atlantic"));
  const hero=put(main,el("div",null,"hero"));
  for(const [label,id] of [["W domu","sensor.room_0_temperatura_pokojowa_strefa_1_2"],["Na zewnątrz","sensor.alfea_extensa_s_temperatura_zewnetrzna_2"],["CWU","sensor.dhw_0_default_temperatura_cwu_2"],["Ciśnienie","sensor.alfea_extensa_s_cisnienie_wody_2"]]){
   const c=put(hero,el("div",null,"card"));put(c,el("span",label,"small"));put(c,el("div",display(this._hass.states[id]),"value"));
  }
  put(main,el("div","COP1 i COP2 są szacunkami diagnostycznymi, nie pomiarami producenta. Brak dzisiejszego odczytu = brak danych, nie zero. Surowe wartości grzałek nie potwierdzają ich załączenia.","warning"));
  const chartGrid=put(main,el("div",null,"grid")),gen=++this._sequence;
  for(const [name,ids] of GRAPHS){const card=put(chartGrid,el("section",null,"card chart"));put(card,el("h2",name));const body=put(card,el("div","Ładowanie historii…","small"));this.history(body,ids,gen);}
  const grid=put(main,el("div",null,"grid"));
  for(const [name,rows] of DATA){const card=put(grid,el("section",null,"card"));put(card,el("h2",name));if(name.includes("Surowe"))put(card,el("p","Jednostki i skala odczytów niepotwierdzone.","small"));for(const [label,id] of rows)put(card,this.row(label,id));}
 }
 async history(target,ids,gen){
  try {
   const end=new Date(),start=new Date(end.getTime()-86400000);
   const answer=await this._hass.callWS({type:"history/history_during_period",start_time:start.toISOString(),end_time:end.toISOString(),entity_ids:ids,minimal_response:true,no_attributes:true});
   if(gen!==this._sequence)return;
   const palette=["#159e87","#e9a24d","#6e9af5"];
   const series=(Array.isArray(answer)?answer:[]).map((rows,i)=>({color:palette[i],label:ids[i].split(".").pop(),data:(Array.isArray(rows)?rows:[]).map(p=>({v:Number(p.s??p.state),t:p.lu?Number(p.lu)*1000:Date.parse(p.last_changed||"")})).filter(p=>Number.isFinite(p.v)&&Number.isFinite(p.t))})).filter(s=>s.data.length);
   if(!series.length){target.textContent="Brak historii w Home Assistant";return;}
   const vals=series.flatMap(s=>s.data.map(p=>p.v)),min=Math.min(...vals),max=Math.max(...vals),range=(max-min)||1;
   const svg=document.createElementNS("http://www.w3.org/2000/svg","svg");svg.setAttribute("viewBox","0 0 320 130");
   for(const s of series){const p=document.createElementNS(svg.namespaceURI,"path");const d=s.data.map((v,i)=>(i?"L":"M")+(12+296*(v.t-start.getTime())/86400000).toFixed(1)+","+(116-104*(v.v-min+range*.1)/(range*1.2)).toFixed(1)).join(" ");p.setAttribute("d",d);p.setAttribute("fill","none");p.setAttribute("stroke",s.color);p.setAttribute("stroke-width","2.5");svg.appendChild(p);}
   target.replaceChildren();put(target,svg);const leg=put(target,el("div",null,"legend"));series.forEach(s=>put(leg,el("span","● "+s.label+"  ")).style.color=s.color);
  }catch(e){if(gen===this._sequence)target.textContent="Historia niedostępna; bieżące odczyty działają niezależnie.";}
 }
}
if(!customElements.get("atlantic-cozytouch-monitor"))customElements.define("atlantic-cozytouch-monitor",AtlanticCozytouchMonitor);
