/*
 * Glass reel: a row of images that drifts sideways on its own and stretches,
 * swells and blurs at the left and right edges, like looking through bent glass.
 * People can drag it (mouse), swipe it (touch) or scroll it sideways (trackpad),
 * and clicking an image calls onOpen with that image's index.
 *
 * No libraries needed. Uses WebGL for the bend; without WebGL it still drifts, just flat.
 *
 *   const reel = glassReel(document.querySelector("#myReel"), [
 *     { src: "a.jpg", ratio: 0.667 },     // ratio = height / width
 *     { src: "b.jpg", ratio: 1.25 },
 *   ], { onOpen: i => console.log("open", i) });
 *
 *   reel.show(false)   // pause it while hidden
 *   reel.show(true)    // start it again
 *   reel.destroy()     // remove it
 *
 * The container gets a canvas and sets its own height from its width.
 *
 * Options (all optional):
 *   speed      drift in px per second (default 42; 0 = still)
 *   hoverSpeed drift while the mouse is over it (default 12)
 *   radius     corner radius of each image in px (default 14)
 *   onOpen     called with the image index when an image is clicked or tapped
 */
(function () {
  const FRAG = `precision mediump float;
varying vec2 v;uniform sampler2D t;uniform float e,a,px,sw;
void main(){
  float x=v.x,y=1.-v.y,d=min(x,1.-x);
  float k=clamp((e-d)/e,0.,1.);                        // 0 in the middle, 1 at the very edge
  float s=e*(k-.45*k*k);                               // near the edges less of the image fills more of the screen: it stretches
  float u=d>=e?x:(x<.5?e-s:1.-e+s);
  float tx=(u-a)/(1.-2.*a),ty=.5+(y-.5)/(1.+sw*k*k);   // and it swells a little
  float sp=k*k*14.*px;                                 // with a sideways smear
  vec4 c=(texture2D(t,vec2(tx-2.*sp,ty))+texture2D(t,vec2(tx-sp,ty))+texture2D(t,vec2(tx,ty))+texture2D(t,vec2(tx+sp,ty))+texture2D(t,vec2(tx+2.*sp,ty)))/5.;
  c.rgb=mix(c.rgb,vec3(c.a),.3*k*k);                   // turning milky
  gl_FragColor=c*smoothstep(0.,.05,d);                 // and fading out at the very edge
}`;
  const SWELL = .15;

  function glassReel(el, images, opts = {}) {
    const calm = matchMedia("(prefers-reduced-motion:reduce)").matches;
    const o = { speed: 42, hoverSpeed: 12, radius: 14, onOpen: null, ...opts };
    const stage = document.createElement("div");
    stage.tabIndex = 0;
    stage.setAttribute("role", "region");
    stage.setAttribute("aria-label", "Image reel. Drag to explore, Enter opens the middle image.");
    stage.style.cssText = "position:relative;cursor:grab;touch-action:pan-y;user-select:none;-webkit-user-select:none;outline:none";
    const rc = document.createElement("canvas");
    rc.style.cssText = "display:block;width:100%;height:100%";
    stage.append(rc); el.append(stage);

    const pics = images.map(m => { const img = new Image(); img.decoding = "async"; img.src = m.src; return { img, ratio: m.ratio || .667 }; });
    const strip = document.createElement("canvas"), sc = strip.getContext("2d");
    const R = { W: 0, H: 0, CH: 0, dpr: 1, e: .2, a: .09, gap: 24, L: 1, pos: 0, vel: 0, items: [],
                on: true, vis: false, raf: 0, drag: null, hover: false, placed: false, last: 0 };

    let gl = null, U = {}, c2 = null;
    try { gl = rc.getContext("webgl", { alpha: true, premultipliedAlpha: true, antialias: false }); } catch (err) { gl = null; }
    if (gl) {
      const sh = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); return s; };
      const pr = gl.createProgram();
      gl.attachShader(pr, sh(gl.VERTEX_SHADER, "attribute vec2 p;varying vec2 v;void main(){v=p*.5+.5;gl_Position=vec4(p,0.,1.);}"));
      gl.attachShader(pr, sh(gl.FRAGMENT_SHADER, FRAG));
      gl.linkProgram(pr);
      if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) gl = null;
      else {
        gl.useProgram(pr);
        gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
        const loc = gl.getAttribLocation(pr, "p");
        gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
        gl.bindTexture(gl.TEXTURE_2D, gl.createTexture());
        [[gl.TEXTURE_MIN_FILTER, gl.LINEAR], [gl.TEXTURE_MAG_FILTER, gl.LINEAR], [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE], [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE]]
          .forEach(([k, val]) => gl.texParameteri(gl.TEXTURE_2D, k, val));
        gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, true);
        ["e", "a", "px", "sw"].forEach(n => U[n] = gl.getUniformLocation(pr, n));
        gl.uniform1f(U.sw, SWELL);
      }
    }
    if (!gl) c2 = rc.getContext("2d");

    function size() {
      const W = stage.clientWidth;
      if (!W) return;
      const small = W < 700, cw = small ? W * .74 : Math.min(W * .46, 640);
      R.W = W; R.CH = cw * .6667; R.H = Math.round(R.CH / .72);
      R.e = gl ? (small ? .13 : .2) : 0; R.a = .45 * R.e; R.gap = small ? 14 : 24;
      stage.style.height = R.H + "px";
      let x = 0;
      R.items = pics.map((p, i) => { const it = { ...p, i, x, w: R.CH / p.ratio }; x += it.w + R.gap; return it; });
      R.L = x || 1;
      R.dpr = Math.min(devicePixelRatio || 1, 2);
      rc.width = Math.round(W * R.dpr); rc.height = Math.round(R.H * R.dpr);
      strip.width = Math.ceil(W * (1 - 2 * R.a) * R.dpr); strip.height = rc.height;
      if (gl) { gl.viewport(0, 0, rc.width, rc.height); gl.uniform1f(U.e, R.e); gl.uniform1f(U.a, R.a); gl.uniform1f(U.px, 1 / strip.width); }
      if (!R.placed && R.items.length) { R.pos = R.items[0].w / 2 - W * (.5 - R.a); R.placed = true; }  // first image starts in the middle
      draw();
    }
    function draw() {
      const d = R.dpr, top = (R.H - R.CH) / 2 * d, rad = o.radius * d, vis = R.W * (1 - 2 * R.a);
      sc.clearRect(0, 0, strip.width, strip.height);
      for (let base = -(((R.pos % R.L) + R.L) % R.L); base < vis; base += R.L) for (const it of R.items) {
        const x = base + it.x;
        if (x > vis || x + it.w < 0) continue;
        sc.save(); sc.beginPath();
        if (sc.roundRect) sc.roundRect(x * d, top, it.w * d, R.CH * d, rad); else sc.rect(x * d, top, it.w * d, R.CH * d);
        sc.clip();
        if (it.img.complete && it.img.naturalWidth) sc.drawImage(it.img, x * d, top, it.w * d, R.CH * d);
        else { sc.fillStyle = "#e4e4e1"; sc.fill(); }
        sc.restore();
      }
      if (gl) {
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, strip);
        gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT); gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      } else { c2.clearRect(0, 0, rc.width, rc.height); c2.drawImage(strip, 0, 0); }
    }
    function frame(t) {
      R.raf = requestAnimationFrame(frame);
      const dt = Math.min(.05, (t - (R.last || t)) / 1000); R.last = t;
      if (!R.drag) {
        const speed = calm ? 0 : R.hover ? o.hoverSpeed : o.speed;
        R.vel += (speed - R.vel) * Math.min(1, dt * 2.2);
        R.pos += R.vel * dt;
      }
      draw();
    }
    function run() {
      const go = R.on && R.vis && !document.hidden;
      if (go && !R.raf) { R.last = 0; R.raf = requestAnimationFrame(frame); }
      else if (!go && R.raf) { cancelAnimationFrame(R.raf); R.raf = 0; }
    }
    function hit(cx, cy) {   // the image under a screen point, undoing the bend
      const r = stage.getBoundingClientRect(), x = (cx - r.left) / r.width, y = (cy - r.top) / r.height;
      const e = R.e, d = Math.min(x, 1 - x), k = e ? Math.max(0, (e - d) / e) : 0, s = e * (k - .45 * k * k);
      const u = d >= e ? x : x < .5 ? e - s : 1 - e + s;
      const py = (.5 + (y - .5) / (1 + SWELL * k * k)) * R.H, top = (R.H - R.CH) / 2;
      if (py < top || py > top + R.CH) return -1;
      const X = ((((u - R.a) * R.W + R.pos) % R.L) + R.L) % R.L;
      const it = R.items.find(it => X >= it.x && X <= it.x + it.w);
      return it ? it.i : -1;
    }
    const open = i => { if (i >= 0 && o.onOpen) o.onOpen(i); };

    const io = new IntersectionObserver(es => { R.vis = es[0].isIntersecting; run(); });
    io.observe(stage);
    const ro = new ResizeObserver(() => { if (stage.clientWidth && stage.clientWidth !== R.W) size(); });
    ro.observe(stage);
    document.addEventListener("visibilitychange", run);
    pics.forEach(p => p.img.addEventListener("load", () => { if (!R.raf) draw(); }));

    stage.addEventListener("pointerdown", e => {
      if (e.button !== 0) return;
      R.drag = { id: e.pointerId, lastX: e.clientX, lastT: performance.now(), moved: 0, v: 0 };
      R.vel = 0;
    });
    stage.addEventListener("pointermove", e => {
      const d = R.drag;
      if (!d || e.pointerId !== d.id) return;
      const dx = e.clientX - d.lastX, now = performance.now();
      R.pos -= dx; d.moved += Math.abs(dx);
      d.v = d.v * .5 + (-dx / Math.max(1, now - d.lastT) * 1000) * .5;
      d.lastX = e.clientX; d.lastT = now;
      if (d.moved > 4) stage.style.cursor = "grabbing";
      if (!R.raf) draw();
    });
    const up = (e, cancel) => {
      const d = R.drag;
      if (!d || e.pointerId !== d.id) return;
      R.drag = null; stage.style.cursor = "grab";
      if (!cancel && d.moved < 6) open(hit(e.clientX, e.clientY));
      else if (performance.now() - d.lastT < 80) R.vel = Math.max(-3000, Math.min(3000, d.v));   // a flick keeps it gliding
    };
    stage.addEventListener("pointerup", e => up(e, false));
    stage.addEventListener("pointercancel", e => up(e, true));
    stage.addEventListener("pointerleave", e => { R.hover = false; if (R.drag && e.pointerType === "mouse") up(e, true); });
    stage.addEventListener("pointerenter", e => { if (e.pointerType === "mouse") R.hover = true; });
    stage.addEventListener("wheel", e => {
      if (Math.abs(e.deltaX) <= Math.abs(e.deltaY)) return;
      e.preventDefault(); R.pos += e.deltaX; if (!R.raf) draw();
    }, { passive: false });
    stage.addEventListener("keydown", e => {
      if (e.key === "ArrowLeft" || e.key === "ArrowRight") { e.preventDefault(); R.vel = e.key === "ArrowLeft" ? -900 : 900; }
      if (e.key === "Enter") { const r = stage.getBoundingClientRect(); open(hit(r.left + r.width / 2, r.top + r.height / 2)); }
    });

    size(); run();
    return {
      show(on) { R.on = on; if (on) size(); run(); },
      destroy() { R.on = false; run(); io.disconnect(); ro.disconnect(); document.removeEventListener("visibilitychange", run); stage.remove(); },
    };
  }

  window.glassReel = glassReel;
})();
