/* Dossier interaction layer (enhancement only; marks are server-rendered).
   Ported from the approved France tile: bottom info panel fade-swap, hover
   dim-siblings + scale, linked highlighting, click-to-expand popover, draw-in.
   Focus mirrors hover; reduced-motion is handled in CSS. */
(function(){
  var info=document.getElementById("info-body");
  if(!info) return;
  var DEFAULT=info.innerHTML;
  function setInfo(h){info.style.opacity=0;setTimeout(function(){info.innerHTML=h;info.style.opacity=1;},110);}
  function clearInfo(){info.style.opacity=0;setTimeout(function(){info.innerHTML=DEFAULT;info.style.opacity=1;},110);}
  function bandMarks(el){var b=el.closest("[data-band]")||el.closest(".hero");return b?b.querySelectorAll(".mk"):[];}
  function enter(el){if(el.dataset.info)setInfo(el.dataset.info);bandMarks(el).forEach(function(s){if(s!==el)s.classList.add("dim");});el.classList.add("hot");}
  function leave(el){bandMarks(el).forEach(function(s){s.classList.remove("dim");});el.classList.remove("hot");clearInfo();}
  function highlight(val){document.querySelectorAll("[data-tags]").forEach(function(m){if((" "+m.dataset.tags+" ").indexOf(" "+val+" ")>-1)m.classList.add("glow");else m.classList.add("faint");});}
  function unhighlight(){document.querySelectorAll(".glow,.faint").forEach(function(m){m.classList.remove("glow","faint");});}
  document.querySelectorAll(".mk, [data-hi]").forEach(function(el){
    var hi=el.dataset.hi;
    el.addEventListener("mouseenter",function(){if(hi){highlight(hi);if(el.dataset.info)setInfo(el.dataset.info);}else enter(el);});
    el.addEventListener("mouseleave",function(){if(hi){unhighlight();clearInfo();}else leave(el);});
    el.addEventListener("focus",function(){if(hi){highlight(hi);if(el.dataset.info)setInfo(el.dataset.info);}else enter(el);});
    el.addEventListener("blur",function(){if(hi){unhighlight();clearInfo();}else leave(el);});
    if(el.dataset.quote||el.dataset.src){
      el.addEventListener("click",function(e){e.preventDefault();e.stopPropagation();openPop(el);});
      el.addEventListener("keydown",function(e){if(e.key==="Enter"||e.key===" "){e.preventDefault();openPop(el);}});
    }
  });
  var pop=document.getElementById("pop"),pq=document.getElementById("pop-q"),
      pm=document.getElementById("pop-m"),ps=document.getElementById("pop-src");
  function openPop(el){
    pq.textContent=el.dataset.quote||"";
    pm.textContent=el.dataset.date||el.dataset.meta||"";
    if(el.dataset.src){ps.style.display="inline-block";ps.href=el.dataset.src;}else ps.style.display="none";
    pop.classList.add("on");
    var r=el.getBoundingClientRect(),pw=Math.min(340,window.innerWidth-24);
    var x=Math.min(Math.max(12,r.left),window.innerWidth-pw-12),y=r.bottom+8;
    if(y+180>window.innerHeight)y=Math.max(12,r.top-190);
    pop.style.left=x+"px";pop.style.top=y+"px";pop.style.maxWidth=pw+"px";
  }
  function closePop(){pop.classList.remove("on");}
  var px=document.getElementById("pop-x");if(px)px.addEventListener("click",closePop);
  document.addEventListener("click",function(e){if(pop&&!pop.contains(e.target))closePop();});
  document.addEventListener("keydown",function(e){if(e.key==="Escape")closePop();});
  if("IntersectionObserver" in window){
    var io=new IntersectionObserver(function(es){es.forEach(function(en){if(en.isIntersecting){en.target.classList.add("in");io.unobserve(en.target);}});},{threshold:.12});
    document.querySelectorAll(".arena").forEach(function(b){io.observe(b);});
  }else document.querySelectorAll(".arena").forEach(function(b){b.classList.add("in");});
})();
