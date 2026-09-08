/* tonecommand.com motion layer.
 *
 * Three things, all optional and all silent when they cannot run:
 *   1. a GPU fluid simulation behind the page (cyan and blue dye drifting on
 *      the near-black ground, stirred by the pointer and by scrolling). The
 *      technique is the classic stable-fluids GPU method (Jos Stam, made
 *      popular on the web by Pavel Dobryakov's WebGL-Fluid-Simulation); the
 *      shaders here are our own compact writing of it.
 *   2. scroll reveals: anything with .reveal fades up when it enters view.
 *   3. the hero command bar types real prompts from the README.
 *
 * Reduced motion turns all three off. The Effect toggle (bottom left) turns
 * the fluid off and remembers it.
 */
(function () {
  'use strict';

  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var KEY = 'tonecommand-fx-off';
  var fxOff = false;
  try { fxOff = localStorage.getItem(KEY) === '1'; } catch (e) { /* private mode */ }

  /* ------------------------------------------------------------------ */
  /* 2. scroll reveals                                                    */
  /* ------------------------------------------------------------------ */
  function reveals() {
    var els = document.querySelectorAll('.reveal');
    if (reduced || !('IntersectionObserver' in window)) {
      for (var i = 0; i < els.length; i++) els[i].classList.add('in');
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); }
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });
    for (var j = 0; j < els.length; j++) io.observe(els[j]);
  }

  /* ------------------------------------------------------------------ */
  /* 3. hero command bar                                                  */
  /* ------------------------------------------------------------------ */
  function typer() {
    var el = document.querySelector('[data-prompts]');
    if (!el) return;
    var prompts;
    try { prompts = JSON.parse(el.getAttribute('data-prompts')); } catch (e) { return; }
    if (!prompts || !prompts.length) return;
    var out = el.querySelector('.typed');
    if (!out) return;
    if (reduced) { out.textContent = prompts[0]; return; }
    var p = 0, c = 0, deleting = false, wait = 0;
    function tick() {
      var text = prompts[p];
      if (wait > 0) { wait--; }
      else if (!deleting) {
        c++; out.textContent = text.slice(0, c);
        if (c >= text.length) { deleting = true; wait = 55; }
      } else {
        c -= 3; if (c < 0) c = 0; out.textContent = text.slice(0, c);
        if (c === 0) { deleting = false; p = (p + 1) % prompts.length; wait = 12; }
      }
      setTimeout(tick, deleting && wait === 0 ? 18 : (wait > 0 ? 40 : 34 + Math.random() * 40));
    }
    tick();
  }

  /* ------------------------------------------------------------------ */
  /* hero panel tilt                                                      */
  /* ------------------------------------------------------------------ */
  function tilt() {
    var panel = document.querySelector('.hero-panel');
    if (!panel || reduced || !window.matchMedia('(pointer: fine)').matches) return;
    var rx = 0, ry = 0, tx = 0, ty = 0, raf = null;
    function frame() {
      rx += (tx - rx) * 0.08; ry += (ty - ry) * 0.08;
      panel.style.transform = 'perspective(1400px) rotateX(' + rx.toFixed(2) + 'deg) rotateY(' + ry.toFixed(2) + 'deg)';
      raf = (Math.abs(tx - rx) > 0.01 || Math.abs(ty - ry) > 0.01) ? requestAnimationFrame(frame) : null;
    }
    window.addEventListener('mousemove', function (e) {
      var r = panel.getBoundingClientRect();
      var cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      tx = Math.max(-6, Math.min(6, -(e.clientY - cy) / 60));
      ty = Math.max(-8, Math.min(8, (e.clientX - cx) / 90));
      if (!raf) raf = requestAnimationFrame(frame);
    }, { passive: true });
    window.addEventListener('mouseleave', function () { tx = 0; ty = 0; if (!raf) raf = requestAnimationFrame(frame); });
  }

  /* ------------------------------------------------------------------ */
  /* effect toggle                                                        */
  /* ------------------------------------------------------------------ */
  function toggleButton(running) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'fx-toggle';
    btn.setAttribute('aria-label', 'Toggle the background effect');
    btn.textContent = running ? 'Effect: on' : 'Effect: off';
    btn.addEventListener('click', function () {
      try { localStorage.setItem(KEY, running ? '1' : '0'); } catch (e) { /* ignore */ }
      location.reload();
    });
    document.body.appendChild(btn);
  }

  /* ------------------------------------------------------------------ */
  /* 1. fluid                                                             */
  /* ------------------------------------------------------------------ */
  function fluid() {
    var canvas = document.createElement('canvas');
    canvas.className = 'fluid-bg';
    canvas.setAttribute('aria-hidden', 'true');
    var params = { alpha: false, depth: false, stencil: false, antialias: false, preserveDrawingBuffer: false };
    var gl = canvas.getContext('webgl2', params);
    var gl2 = !!gl;
    if (!gl) gl = canvas.getContext('webgl', params) || canvas.getContext('experimental-webgl', params);
    if (!gl) return false;

    var halfFloat, linear;
    if (gl2) {
      gl.getExtension('EXT_color_buffer_float');
      linear = !!gl.getExtension('OES_texture_float_linear');
    } else {
      halfFloat = gl.getExtension('OES_texture_half_float');
      linear = !!gl.getExtension('OES_texture_half_float_linear');
      if (!halfFloat) return false;
    }
    var texType = gl2 ? gl.HALF_FLOAT : halfFloat.HALF_FLOAT_OES;
    var fmt = gl2
      ? { rgba: [gl.RGBA16F, gl.RGBA], rg: [gl.RG16F, gl.RG], r: [gl.R16F, gl.RED] }
      : { rgba: [gl.RGBA, gl.RGBA], rg: [gl.RGBA, gl.RGBA], r: [gl.RGBA, gl.RGBA] };

    function supported(internal, format) {
      var tex = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, tex);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.texImage2D(gl.TEXTURE_2D, 0, internal, 4, 4, 0, format, texType, null);
      var fbo = gl.createFramebuffer();
      gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
      gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
      var ok = gl.checkFramebufferStatus(gl.FRAMEBUFFER) === gl.FRAMEBUFFER_COMPLETE;
      gl.deleteTexture(tex); gl.deleteFramebuffer(fbo);
      return ok;
    }
    if (!supported(fmt.rgba[0], fmt.rgba[1])) return false;
    if (gl2 && !supported(fmt.rg[0], fmt.rg[1])) fmt.rg = fmt.rgba;
    if (gl2 && !supported(fmt.r[0], fmt.r[1])) fmt.r = fmt.rgba;

    document.body.prepend(canvas);
    document.documentElement.classList.add('fx-on');

    var C = {
      SIM: 112, DYE: 640, DENSITY_DISSIPATION: 0.9, VELOCITY_DISSIPATION: 0.35,
      PRESSURE: 0.8, PRESSURE_ITER: 16, CURL: 18, RADIUS: 0.24
    };

    var VERT = [
      'precision highp float; attribute vec2 aPosition; varying vec2 vUv; varying vec2 vL; varying vec2 vR; varying vec2 vT; varying vec2 vB; uniform vec2 texelSize;',
      'void main(){ vUv = aPosition * 0.5 + 0.5; vL = vUv - vec2(texelSize.x, 0.0); vR = vUv + vec2(texelSize.x, 0.0); vT = vUv + vec2(0.0, texelSize.y); vB = vUv - vec2(0.0, texelSize.y); gl_Position = vec4(aPosition, 0.0, 1.0); }'
    ].join('\n');
    var HEAD = 'precision highp float; precision highp sampler2D; varying vec2 vUv; varying vec2 vL; varying vec2 vR; varying vec2 vT; varying vec2 vB;';
    var FRAG = {
      copy: HEAD + 'uniform sampler2D uTexture; void main(){ gl_FragColor = texture2D(uTexture, vUv); }',
      splat: HEAD + 'uniform sampler2D uTarget; uniform float aspectRatio; uniform vec3 color; uniform vec2 point; uniform float radius;'
        + 'void main(){ vec2 p = vUv - point.xy; p.x *= aspectRatio; vec3 splat = exp(-dot(p, p) / radius) * color; vec3 base = texture2D(uTarget, vUv).xyz; gl_FragColor = vec4(base + splat, 1.0); }',
      advection: HEAD + 'uniform sampler2D uVelocity; uniform sampler2D uSource; uniform vec2 texelSize; uniform vec2 dyeTexelSize; uniform float dt; uniform float dissipation;'
        + 'vec4 bilerp(sampler2D sam, vec2 uv, vec2 tsize){ vec2 st = uv / tsize - 0.5; vec2 iuv = floor(st); vec2 fuv = fract(st); vec4 a = texture2D(sam, (iuv + vec2(0.5, 0.5)) * tsize); vec4 b = texture2D(sam, (iuv + vec2(1.5, 0.5)) * tsize); vec4 c = texture2D(sam, (iuv + vec2(0.5, 1.5)) * tsize); vec4 d = texture2D(sam, (iuv + vec2(1.5, 1.5)) * tsize); return mix(mix(a, b, fuv.x), mix(c, d, fuv.x), fuv.y); }'
        + 'void main(){ vec2 coord = vUv - dt * bilerp(uVelocity, vUv, texelSize).xy * texelSize; vec4 result = bilerp(uSource, coord, dyeTexelSize); float decay = 1.0 + dissipation * dt; gl_FragColor = result / decay; }',
      divergence: HEAD + 'uniform sampler2D uVelocity;'
        + 'void main(){ float L = texture2D(uVelocity, vL).x; float R = texture2D(uVelocity, vR).x; float T = texture2D(uVelocity, vT).y; float B = texture2D(uVelocity, vB).y; vec2 C = texture2D(uVelocity, vUv).xy; if (vL.x < 0.0) { L = -C.x; } if (vR.x > 1.0) { R = -C.x; } if (vT.y > 1.0) { T = -C.y; } if (vB.y < 0.0) { B = -C.y; } float div = 0.5 * (R - L + T - B); gl_FragColor = vec4(div, 0.0, 0.0, 1.0); }',
      curl: HEAD + 'uniform sampler2D uVelocity;'
        + 'void main(){ float L = texture2D(uVelocity, vL).y; float R = texture2D(uVelocity, vR).y; float T = texture2D(uVelocity, vT).x; float B = texture2D(uVelocity, vB).x; float vorticity = R - L - T + B; gl_FragColor = vec4(0.5 * vorticity, 0.0, 0.0, 1.0); }',
      vorticity: HEAD + 'uniform sampler2D uVelocity; uniform sampler2D uCurl; uniform float curl; uniform float dt;'
        + 'void main(){ float L = texture2D(uCurl, vL).x; float R = texture2D(uCurl, vR).x; float T = texture2D(uCurl, vT).x; float B = texture2D(uCurl, vB).x; float C = texture2D(uCurl, vUv).x; vec2 force = 0.5 * vec2(abs(T) - abs(B), abs(R) - abs(L)); force /= length(force) + 0.0001; force *= curl * C; force.y *= -1.0; vec2 velocity = texture2D(uVelocity, vUv).xy; velocity += force * dt; velocity = min(max(velocity, -1000.0), 1000.0); gl_FragColor = vec4(velocity, 0.0, 1.0); }',
      pressure: HEAD + 'uniform sampler2D uPressure; uniform sampler2D uDivergence;'
        + 'void main(){ float L = texture2D(uPressure, vL).x; float R = texture2D(uPressure, vR).x; float T = texture2D(uPressure, vT).x; float B = texture2D(uPressure, vB).x; float divergence = texture2D(uDivergence, vUv).x; float pressure = (L + R + B + T - divergence) * 0.25; gl_FragColor = vec4(pressure, 0.0, 0.0, 1.0); }',
      gradient: HEAD + 'uniform sampler2D uPressure; uniform sampler2D uVelocity;'
        + 'void main(){ float L = texture2D(uPressure, vL).x; float R = texture2D(uPressure, vR).x; float T = texture2D(uPressure, vT).x; float B = texture2D(uPressure, vB).x; vec2 velocity = texture2D(uVelocity, vUv).xy; velocity.xy -= vec2(R - L, T - B); gl_FragColor = vec4(velocity, 0.0, 1.0); }',
      display: HEAD + 'uniform sampler2D uTexture; uniform vec3 bg;'
        + 'void main(){ vec3 c = texture2D(uTexture, vUv).rgb; c = c / (1.0 + c); float vig = smoothstep(1.35, 0.35, length(vUv - 0.5)); gl_FragColor = vec4(bg + c * vig, 1.0); }'
    };

    function compile(type, src) {
      var s = gl.createShader(type);
      gl.shaderSource(s, src); gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) { return null; }
      return s;
    }
    var vs = compile(gl.VERTEX_SHADER, VERT);
    if (!vs) return false;
    function program(fragSrc) {
      var fs = compile(gl.FRAGMENT_SHADER, fragSrc);
      if (!fs) return null;
      var p = gl.createProgram();
      gl.attachShader(p, vs); gl.attachShader(p, fs); gl.linkProgram(p);
      if (!gl.getProgramParameter(p, gl.LINK_STATUS)) return null;
      var u = {}, n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
      for (var i = 0; i < n; i++) { var name = gl.getActiveUniform(p, i).name; u[name] = gl.getUniformLocation(p, name); }
      return { p: p, u: u };
    }
    var P = {};
    for (var k in FRAG) { P[k] = program(FRAG[k]); if (!P[k]) return false; }

    var quad = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, quad);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, -1, 1, 1, 1, 1, -1]), gl.STATIC_DRAW);
    var idx = gl.createBuffer();
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, idx);
    gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Uint16Array([0, 1, 2, 0, 2, 3]), gl.STATIC_DRAW);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    gl.enableVertexAttribArray(0);
    function blit(target) {
      if (target == null) { gl.viewport(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight); gl.bindFramebuffer(gl.FRAMEBUFFER, null); }
      else { gl.viewport(0, 0, target.w, target.h); gl.bindFramebuffer(gl.FRAMEBUFFER, target.fbo); }
      gl.drawElements(gl.TRIANGLES, 6, gl.UNSIGNED_SHORT, 0);
    }

    function fbo(w, h, f, filter) {
      gl.activeTexture(gl.TEXTURE0);
      var tex = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, tex);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, filter);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, filter);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.texImage2D(gl.TEXTURE_2D, 0, f[0], w, h, 0, f[1], texType, null);
      var fb = gl.createFramebuffer();
      gl.bindFramebuffer(gl.FRAMEBUFFER, fb);
      gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
      gl.viewport(0, 0, w, h); gl.clear(gl.COLOR_BUFFER_BIT);
      return { tex: tex, fbo: fb, w: w, h: h, tx: 1 / w, ty: 1 / h,
        attach: function (id) { gl.activeTexture(gl.TEXTURE0 + id); gl.bindTexture(gl.TEXTURE_2D, tex); return id; } };
    }
    function dfbo(w, h, f, filter) {
      var a = fbo(w, h, f, filter), b = fbo(w, h, f, filter);
      return { w: w, h: h, tx: a.tx, ty: a.ty, get read() { return a; }, get write() { return b; }, swap: function () { var t = a; a = b; b = t; } };
    }
    function res(base) {
      var ar = gl.drawingBufferWidth / gl.drawingBufferHeight;
      if (ar < 1) ar = 1 / ar;
      var min = Math.round(base), max = Math.round(base * ar);
      return gl.drawingBufferWidth > gl.drawingBufferHeight ? { w: max, h: min } : { w: min, h: max };
    }
    var filt = linear ? gl.LINEAR : gl.NEAREST;
    var dye, vel, div, curl, pres;
    function init() {
      var s = res(C.SIM), d = res(C.DYE);
      dye = dfbo(d.w, d.h, fmt.rgba, filt);
      vel = dfbo(s.w, s.h, fmt.rg, filt);
      div = fbo(s.w, s.h, fmt.r, gl.NEAREST);
      curl = fbo(s.w, s.h, fmt.r, gl.NEAREST);
      pres = dfbo(s.w, s.h, fmt.r, gl.NEAREST);
    }
    function resize() {
      var dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      var w = Math.floor(canvas.clientWidth * dpr), h = Math.floor(canvas.clientHeight * dpr);
      if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; init(); }
    }
    resize();

    function use(pr) { gl.useProgram(pr.p); return pr; }
    function splat(x, y, dx, dy, color) {
      var pr = use(P.splat);
      gl.uniform1i(pr.u.uTarget, vel.read.attach(0));
      gl.uniform1f(pr.u.aspectRatio, canvas.width / canvas.height);
      gl.uniform2f(pr.u.point, x, y);
      gl.uniform3f(pr.u.color, dx, dy, 0);
      gl.uniform1f(pr.u.radius, C.RADIUS / 100);
      blit(vel.write); vel.swap();
      gl.uniform1i(pr.u.uTarget, dye.read.attach(0));
      gl.uniform3f(pr.u.color, color[0], color[1], color[2]);
      blit(dye.write); dye.swap();
    }
    /* brand dye: cyan, blue, a little purple; all dim so text stays readable */
    var PALETTE = [[0.06, 0.34, 0.40], [0.10, 0.20, 0.42], [0.20, 0.12, 0.40], [0.04, 0.30, 0.30]];
    function pick(scale) { var c = PALETTE[Math.floor(Math.random() * PALETTE.length)]; return [c[0] * scale, c[1] * scale, c[2] * scale]; }

    function step(dt) {
      gl.disable(gl.BLEND);
      var pr = use(P.curl);
      gl.uniform2f(pr.u.texelSize, vel.tx, vel.ty);
      gl.uniform1i(pr.u.uVelocity, vel.read.attach(0));
      blit(curl);
      pr = use(P.vorticity);
      gl.uniform2f(pr.u.texelSize, vel.tx, vel.ty);
      gl.uniform1i(pr.u.uVelocity, vel.read.attach(0));
      gl.uniform1i(pr.u.uCurl, curl.attach(1));
      gl.uniform1f(pr.u.curl, C.CURL);
      gl.uniform1f(pr.u.dt, dt);
      blit(vel.write); vel.swap();
      pr = use(P.divergence);
      gl.uniform2f(pr.u.texelSize, vel.tx, vel.ty);
      gl.uniform1i(pr.u.uVelocity, vel.read.attach(0));
      blit(div);
      pr = use(P.copy);
      gl.uniform1i(pr.u.uTexture, pres.read.attach(0));
      /* damp pressure between frames instead of clearing: cheaper, same look */
      blit(pres.write); pres.swap();
      pr = use(P.pressure);
      gl.uniform2f(pr.u.texelSize, vel.tx, vel.ty);
      gl.uniform1i(pr.u.uDivergence, div.attach(0));
      for (var i = 0; i < C.PRESSURE_ITER; i++) {
        gl.uniform1i(pr.u.uPressure, pres.read.attach(1));
        blit(pres.write); pres.swap();
      }
      pr = use(P.gradient);
      gl.uniform2f(pr.u.texelSize, vel.tx, vel.ty);
      gl.uniform1i(pr.u.uPressure, pres.read.attach(0));
      gl.uniform1i(pr.u.uVelocity, vel.read.attach(1));
      blit(vel.write); vel.swap();
      pr = use(P.advection);
      gl.uniform2f(pr.u.texelSize, vel.tx, vel.ty);
      gl.uniform2f(pr.u.dyeTexelSize, vel.tx, vel.ty);
      var v = vel.read.attach(0);
      gl.uniform1i(pr.u.uVelocity, v);
      gl.uniform1i(pr.u.uSource, v);
      gl.uniform1f(pr.u.dt, dt);
      gl.uniform1f(pr.u.dissipation, C.VELOCITY_DISSIPATION);
      blit(vel.write); vel.swap();
      gl.uniform2f(pr.u.dyeTexelSize, dye.tx, dye.ty);
      gl.uniform1i(pr.u.uVelocity, vel.read.attach(0));
      gl.uniform1i(pr.u.uSource, dye.read.attach(1));
      gl.uniform1f(pr.u.dissipation, C.DENSITY_DISSIPATION);
      blit(dye.write); dye.swap();
    }
    function render() {
      var pr = use(P.display);
      gl.uniform1i(pr.u.uTexture, dye.read.attach(0));
      gl.uniform3f(pr.u.bg, 0.051, 0.059, 0.051); /* #0d0f0d */
      blit(null);
    }

    /* stirring: ambient drift, the pointer, and the scroll wheel */
    var last = performance.now(), ambientAt = 0, px = 0.5, py = 0.5, pdown = false, lastScroll = window.scrollY;
    var hidden = false;
    document.addEventListener('visibilitychange', function () { hidden = document.hidden; });
    window.addEventListener('mousemove', function (e) {
      var x = e.clientX / canvas.clientWidth, y = 1 - e.clientY / canvas.clientHeight;
      var dx = (x - px) * 600, dy = (y - py) * 600;
      px = x; py = y;
      if (Math.abs(dx) + Math.abs(dy) > 0.5) splat(x, y, dx, dy, pick(0.55));
    }, { passive: true });
    window.addEventListener('scroll', function () {
      var d = window.scrollY - lastScroll; lastScroll = window.scrollY;
      if (Math.abs(d) < 2) return;
      var n = Math.min(3, Math.ceil(Math.abs(d) / 120));
      for (var i = 0; i < n; i++) {
        var x = Math.random();
        splat(x, Math.random() < 0.5 ? 0.02 : 0.98, (Math.random() - 0.5) * 200, -d * 6, pick(0.6));
      }
    }, { passive: true });
    window.addEventListener('resize', resize);

    /* a first breath so the page is never a flat black on arrival */
    for (var s0 = 0; s0 < 5; s0++) splat(Math.random(), Math.random(), (Math.random() - 0.5) * 500, (Math.random() - 0.5) * 500, pick(1.4));

    function loop(now) {
      var dt = Math.min((now - last) / 1000, 1 / 30); last = now;
      if (!hidden) {
        if (now > ambientAt) {
          ambientAt = now + 900 + Math.random() * 1400;
          splat(Math.random(), Math.random() * 0.6 + 0.2, (Math.random() - 0.5) * 260, (Math.random() - 0.5) * 260, pick(1.4));
        }
        step(dt); render();
      }
      requestAnimationFrame(loop);
    }
    requestAnimationFrame(loop);
    return true;
  }

  function start() {
    reveals(); typer(); tilt();
    if (reduced) return;
    var running = false;
    if (!fxOff) { try { running = fluid(); } catch (e) { running = false; } }
    if (running || fxOff) toggleButton(running);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
