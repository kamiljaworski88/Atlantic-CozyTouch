/* Atlantic CozyTouch monitoring panel. Uses HA-provided state only, no network access. */
const GROUPS = [
  ["Komfort i temperatury", /temperatur|temperature|room|pokoj|zasilani|powrot|zewnetrz/i],
  ["Ogrzewanie CO", /\\bco\\b|ogrzewani|heating|obieg|krzyw/i],
  ["Ciepła woda CWU", /cwu|ciep.a woda|hot.water|dhw|zasobnik/i],
  ["Energia i COP", /energia|energy|cop|electric|elektrycz|ciepl|produkcj|kwh/i],
  ["Sprężarka i grzałki", /spr.zark|compressor|grza.k|heater|defrost|odszran/i],
  ["Diagnostyka Atlantic", /api|diagnost|status|parametr|odczyt|probe|support|freshness|quality|pokrycie/i]
];
function belongs(s) {
  const id = s.entity_id.toLowerCase(), name = (s.attributes.friendly_name || "").toLowerCase();
  return /^(sensor|binary_sensor)\\./.test(id) &&
    (/atlantic|cozytouch|alfea|extensa/.test(id) || /atlantic|cozytouch|alfea|extensa/.test(name));
}
function div(tag, cls, label) {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  if (label != null) el.textContent = label;
  return el;
}
class AtlanticCozytouchMonitor extends HTMLElement {
  constructor() { super(); this.attachShadow({mode:"open"}); this._hass = null; this._last = ""; }
  set hass(value) {
    this._hass = value;
    if (!this.isConnected) return;
    const sensors = Object.values(value.states).filter(belongs);
    const key = sensors.map(s => [s.entity_id,s.state].join("=")).join("|");
    if (key !== this._last) { this._last = key; this.draw(sensors); }
  }
  connectedCallback() { if (this._hass) this.draw(Object.values(this._hass.states).filter(belongs)); }
  draw(sensors) {
    const root=this.shadowRoot;
    root.replaceChildren();
    const css=div("style");
    css.textContent=`:host{display:block;padding:16px;color:var(--primary-text-color);font-family:var(--primary-font-family,Arial,sans-serif);box-sizing:border-box}h1{font-size:24px;margin:6px 0 2px}.hint{color:var(--secondary-text-color);margin-bottom:22px}main{max-width:1400px;margin:auto}.layout{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr));gap:16px}.group{background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:14px;padding:16px;min-width:0}h2{font-size:17px;margin:0 0 12px}.metric{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:10px 0;border-top:1px solid var(--divider-color);cursor:pointer;line-height:1.35}.metric:hover{opacity:.8}.metric span{font-size:13px;min-width:0;overflow-wrap:anywhere}.metric strong{font-size:15px;text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}.empty{color:var(--secondary-text-color);font-size:13px}.warning{color:var(--error-color);font-size:13px;margin:8px 0}button{border:0;background:var(--primary-color);color:white;padding:9px 12px;border-radius:9px;cursor:pointer}`;
    root.append(css);
    const main=div("main");main.append(div("h1",null,"Atlantic · pompa ciepła"));
    main.append(div("p","hint","Automatyczny podgląd tylko do odczytu · dane z encji Home Assistant"));
    if (!sensors.length) { main.append(div("p","warning","Brak wykrytych encji Atlantic. Sprawdź połączenie integracji i nazwy urządzeń."));root.append(main);return; }
    const layout=div("div","layout");
    const allocated=new Set();
    for(const [title,re] of GROUPS){
      const group=div("section","group");group.append(div("h2",null,title));
      const matches=sensors.filter(s=>re.test(s.entity_id+" "+(s.attributes.friendly_name||"")));
      for(const s of matches){allocated.add(s.entity_id);group.append(this.metric(s));}
      if(!matches.length)group.append(div("p","empty","Brak danych w tej kategorii."));
      layout.append(group);
    }
    const others=sensors.filter(s=>!allocated.has(s.entity_id));
    if(others.length){const group=div("section","group");group.append(div("h2",null,"Pozostałe parametry"));for(const s of others)group.append(this.metric(s));layout.append(group);}
    main.append(layout);root.append(main);
  }
  metric(s) {
    const el=div("div","metric"), name=div("span",null,s.attributes.friendly_name||s.entity_id);
    const val=s.state==="unknown"||s.state==="unavailable"?"Brak danych":s.state;
    const unit=s.attributes.unit_of_measurement;
    const strong=div("strong",null,val+(unit&&val!=="Brak danych"?" "+unit:""));
    el.append(name,strong);el.setAttribute("role","button");el.tabIndex=0;
    const show=()=>this.dispatchEvent(new CustomEvent("hass-more-info",{bubbles:true,composed:true,detail:{entityId:s.entity_id}}));
    el.addEventListener("click",show);
    el.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();show();}});
    return el;
  }
}
if(!customElements.get("atlantic-cozytouch-monitor"))customElements.define("atlantic-cozytouch-monitor",AtlanticCozytouchMonitor);
