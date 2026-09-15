'use client';

import { useEffect, useRef, useState } from 'react';
import { Pause, Play } from 'lucide-react';

/** The fallback and live view share the same Blender model and framing. */
export function DossierScene() {
  const host = useRef<HTMLDivElement>(null);
  const pausedRef = useRef(false);
  const refresh = useRef<() => void>(() => {});
  const [paused, setPaused] = useState(false);
  const [status, setStatus] = useState<'loading' | 'ready' | 'fallback'>('loading');

  useEffect(() => { pausedRef.current = paused; refresh.current(); }, [paused]);
  useEffect(() => {
    const element = host.current!;
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    pausedRef.current = motion.matches;
    setPaused(motion.matches);
    const changeMotion = () => setPaused(motion.matches);
    motion.addEventListener('change', changeMotion);
    let disposed = false;
    let release = () => {};
    const abort = new AbortController();

    async function mount() {
      try {
        const [THREE, { GLTFLoader }, { RoomEnvironment }] = await Promise.all([
          import('three'), import('three/addons/loaders/GLTFLoader.js'),
          import('three/addons/environments/RoomEnvironment.js'),
        ]);
        if (disposed) return;
        const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, preserveDrawingBuffer: true, powerPreference: 'low-power' });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
        renderer.setClearColor(0x000000, 0);
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1;
        renderer.domElement.setAttribute('aria-hidden', 'true');
        element.appendChild(renderer.domElement);
        release = () => { renderer.dispose(); renderer.domElement.remove(); };
        const scene = new THREE.Scene();
        const camera = new THREE.OrthographicCamera(-3, 3, 2.55, -2.55, .1, 40);
        camera.position.set(4.4, 5, 10.7);
        camera.lookAt(0, 1.82, 0);
        const pmrem = new THREE.PMREMGenerator(renderer);
        const room = new RoomEnvironment();
        const environment = pmrem.fromScene(room, .04);
        scene.environment = environment.texture;
        scene.environmentIntensity = .65;
        room.dispose();
        pmrem.dispose();
        scene.add(new THREE.HemisphereLight(0xe9f3ff, 0x302a24, .8));
        const key = new THREE.DirectionalLight(0xffe4bb, 2);
        key.position.set(3, 4, 4);
        scene.add(key);
        const fill = new THREE.DirectionalLight(0xb8d5f3, 1);
        fill.position.set(-4, 3, 2);
        scene.add(fill);
        const sculpture = new THREE.Group();
        scene.add(sculpture);
        let frame = 0, last = 0, elapsed = 0;
        let visible = true;
        let pointerX = 0, pointerY = 0;
        let ready = false;
        const disposeModel = (model: import('three').Object3D) => model.traverse(object => {
          if (object instanceof THREE.Mesh) {
            object.geometry.dispose();
            const materials = Array.isArray(object.material) ? object.material : [object.material];
            materials.forEach(material => material.dispose());
          }
        });
        function draw(now: number) {
          frame = 0;
          if (disposed || !ready || !visible || document.hidden) return;
          const delta = Math.min((now - last) / 1000, .05);
          if (!pausedRef.current) {
            elapsed += delta;
            sculpture.rotation.y += ((Math.sin(elapsed * .28) * .075 + pointerX * .12) - sculpture.rotation.y) * .07;
            sculpture.rotation.x += ((pointerY * .035) - sculpture.rotation.x) * .07;
            sculpture.position.y = Math.sin(elapsed * .55) * .022;
          }
          last = now;
          renderer.render(scene, camera);
          if (!pausedRef.current) frame = requestAnimationFrame(draw);
        }
        const wake = () => { if (!frame && !disposed) frame = requestAnimationFrame(draw); };
        refresh.current = wake;
        const resize = () => {
          const width = element.clientWidth, height = element.clientHeight;
          if (!width || !height) return;
          const aspect = width / height;
          const vertical = Math.max(4.5, 5.7 / aspect);
          camera.left = -vertical * aspect / 2;
          camera.right = vertical * aspect / 2;
          camera.top = vertical / 2;
          camera.bottom = -vertical / 2;
          camera.updateProjectionMatrix();
          renderer.setSize(width, height);
          wake();
        };
        const resizeObserver = new ResizeObserver(resize);
        resizeObserver.observe(element);
        const visibility = new IntersectionObserver(entries => { visible = entries[0].isIntersecting; wake(); });
        visibility.observe(element);
        const pointer = (event: PointerEvent) => {
          if (event.pointerType !== 'mouse' || pausedRef.current) return;
          const rect = element.getBoundingClientRect();
          pointerX = ((event.clientX - rect.left) / rect.width - .5) * 2;
          pointerY = ((event.clientY - rect.top) / rect.height - .5) * 2;
        };
        const leave = () => { pointerX = 0; pointerY = 0; };
        const contextLost = (event: Event) => { event.preventDefault(); setStatus('fallback'); release(); };
        element.addEventListener('pointermove', pointer);
        element.addEventListener('pointerleave', leave);
        renderer.domElement.addEventListener('webglcontextlost', contextLost);
        document.addEventListener('visibilitychange', wake);
        let released = false;
        release = () => {
          if (released) return;
          released = true;
          ready = false;
          cancelAnimationFrame(frame);
          resizeObserver.disconnect();
          visibility.disconnect();
          element.removeEventListener('pointermove', pointer);
          element.removeEventListener('pointerleave', leave);
          document.removeEventListener('visibilitychange', wake);
          renderer.domElement.removeEventListener('webglcontextlost', contextLost);
          disposeModel(sculpture);
          environment.dispose();
          renderer.dispose();
          renderer.domElement.remove();
          refresh.current = () => {};
        };
        const response = await fetch('/models/sabc-dossier.glb', { signal: abort.signal });
        if (!response.ok) throw new Error('Model unavailable');
        const gltf = await new GLTFLoader().parseAsync(await response.arrayBuffer(), '/models/');
        if (disposed || released) { disposeModel(gltf.scene); return; }
        sculpture.add(gltf.scene);
        ready = true;
        setStatus('ready');
        resize();
      } catch {
        release();
        if (!disposed) setStatus('fallback');
      }
    }
    // Do not load the renderer until the sculpture is near the viewport.
    const observer = new IntersectionObserver(entries => {
      if (entries[0].isIntersecting) { observer.disconnect(); void mount(); }
    }, { rootMargin: '120px' });
    observer.observe(element);
    return () => {
      disposed = true;
      abort.abort();
      observer.disconnect();
      motion.removeEventListener('change', changeMotion);
      release();
    };
  }, []);

  return <figure className="dossier-figure" data-scene-state={status}>
    <div className="dossier-viewport" ref={host} role="img" aria-label="三维项目评估档案：项目资料与证据汇入八维评估，形成 S、A、B、C 评级建议">
      <img className={'dossier-poster ' + (status === 'ready' ? 'is-hidden' : '')} src="/models/sabc-dossier.png" width={1000} height={850} alt="" />
    </div>
    <figcaption><span>资料 <i>→</i> 八维判断 <i>→</i> 评级建议</span>{status === 'ready' && <button type="button" className="scene-toggle" aria-label={paused ? '播放三维模型动画' : '暂停三维模型动画'} aria-pressed={paused} onClick={() => setPaused(value => !value)}>{paused ? <Play size={12} /> : <Pause size={12} />}</button>}</figcaption>
  </figure>;
}
