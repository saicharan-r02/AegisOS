import * as THREE from 'three'

export type StageId = 'fetch' | 'analyze' | 'solve' | 'guide'
export type StageState = 'pending' | 'active' | 'done' | 'error'
export type SceneMode = 'idle' | 'working' | 'done' | 'error'
export type SceneFocus = 'hero' | 'results'

export const STAGE_ORDER: readonly StageId[] = ['fetch', 'analyze', 'solve', 'guide']

const STAGE_LABEL: Record<StageId, string> = {
  fetch: 'Issue',
  analyze: 'Analyze',
  solve: 'Fix',
  guide: 'Pull request',
}

export interface SceneController {
  setStage(stage: StageId, state: StageState): void
  setMode(mode: SceneMode): void
  setFocus(focus: SceneFocus): void
  reset(): void
  dispose(): void
}

interface StageNode {
  id: StageId
  group: THREE.Group
  mat: THREE.MeshStandardMaterial
  halo: THREE.Sprite
  state: StageState
  flash: number
}

const damp = (current: number, target: number, rate: number, dt: number) =>
  current + (target - current) * (1 - Math.exp(-rate * dt))

function glowTexture(): THREE.CanvasTexture {
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = 128
  const ctx = canvas.getContext('2d')!
  const gradient = ctx.createRadialGradient(64, 64, 0, 64, 64, 64)
  gradient.addColorStop(0, 'rgba(255,255,255,1)')
  gradient.addColorStop(0.25, 'rgba(255,255,255,0.45)')
  gradient.addColorStop(1, 'rgba(255,255,255,0)')
  ctx.fillStyle = gradient
  ctx.fillRect(0, 0, 128, 128)
  return new THREE.CanvasTexture(canvas)
}

function labelTexture(text: string): THREE.CanvasTexture {
  const canvas = document.createElement('canvas')
  canvas.width = 512
  canvas.height = 128
  const ctx = canvas.getContext('2d')!
  ctx.font = '600 52px system-ui, -apple-system, sans-serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.clearRect(0, 0, 512, 128)
  ctx.shadowColor = 'rgba(0,0,0,0.85)'
  ctx.shadowBlur = 14
  ctx.fillStyle = '#e7edf7'
  ctx.fillText(text, 256, 64)
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  return texture
}

/** Release GPU resources of everything in the scene. */
function disposeScene(scene: THREE.Scene): void {
  scene.traverse((object) => {
    if ('geometry' in object) (object.geometry as THREE.BufferGeometry).dispose()
    if ('material' in object) {
      const materials = [object.material].flat() as Array<THREE.Material & { map?: THREE.Texture | null }>
      for (const material of materials) {
        material.map?.dispose()
        material.dispose()
      }
    }
  })
}

/**
 * Animated background: a core with an orbit of four pipeline stages and a packet
 * travelling along it. Returns null when WebGL is unavailable.
 */
export function createScene(canvas: HTMLCanvasElement): SceneController | null {
  let renderer: THREE.WebGLRenderer
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance' })
  } catch {
    return null
  }

  const COLOR = {
    accent: new THREE.Color('#a371f7'),
    fetch: new THREE.Color('#3fb950'),
    analyze: new THREE.Color('#4cc2ff'),
    solve: new THREE.Color('#e3b341'),
    guide: new THREE.Color('#a371f7'),
    idle: new THREE.Color('#3a4660'),
    error: new THREE.Color('#f85149'),
    dust: new THREE.Color('#9fb4ff'),
  }

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.setClearColor(0x000000, 0)

  const scene = new THREE.Scene()
  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 120)
  camera.position.set(0, 0.8, 15)
  const world = new THREE.Group()
  scene.add(world)

  scene.add(new THREE.HemisphereLight(0x9bb4ff, 0x1a1030, 1.1))
  const key = new THREE.DirectionalLight(0xffffff, 2.4)
  key.position.set(4, 6, 8)
  scene.add(key)
  const rim = new THREE.DirectionalLight(COLOR.accent, 2.2)
  rim.position.set(-6, -2, -4)
  scene.add(rim)

  const core = new THREE.Group()
  world.add(core)
  const solidMat = new THREE.MeshStandardMaterial({
    color: 0x18213a,
    emissive: COLOR.accent,
    emissiveIntensity: 0.28,
    flatShading: true,
    metalness: 0.45,
    roughness: 0.35,
  })
  const solid = new THREE.Mesh(new THREE.IcosahedronGeometry(1.45, 1), solidMat)
  const wireMat = new THREE.LineBasicMaterial({ color: COLOR.accent, transparent: true, opacity: 0.6 })
  const wire = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.IcosahedronGeometry(2.05, 1)), wireMat)
  const wire2Mat = new THREE.LineBasicMaterial({ color: COLOR.accent, transparent: true, opacity: 0.22 })
  const wire2 = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.IcosahedronGeometry(2.7, 0)), wire2Mat)
  core.add(solid, wire, wire2)

  const rings = [0, 1].map((i) => {
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(3.3 + i * 0.45, 0.012, 8, 180),
      new THREE.MeshBasicMaterial({ color: i ? COLOR.analyze : COLOR.accent, transparent: true, opacity: 0.4 }),
    )
    ring.rotation.set(Math.PI / 2.3 + i * 0.5, i * 0.9, 0)
    core.add(ring)
    return ring
  })

  const orbit = new THREE.CatmullRomCurve3(
    Array.from({ length: 72 }, (_, i) => {
      const a = Math.PI * 1.25 + (i / 72) * Math.PI * 2
      return new THREE.Vector3(Math.cos(a) * 6.2, -Math.sin(a) * 1.7 + Math.sin(a * 2) * 0.25, Math.sin(a) * 2.7)
    }),
    true,
  )
  const TUBE_SEGMENTS = 260
  const RADIAL = 6
  const baseTube = new THREE.Mesh(
    new THREE.TubeGeometry(orbit, TUBE_SEGMENTS, 0.022, RADIAL, true),
    new THREE.MeshBasicMaterial({ color: 0x8b9cff, transparent: true, opacity: 0.3, depthWrite: false }),
  )
  const doneTubeGeo = new THREE.TubeGeometry(orbit, TUBE_SEGMENTS, 0.045, RADIAL, true)
  const doneTube = new THREE.Mesh(
    doneTubeGeo,
    new THREE.MeshBasicMaterial({ color: COLOR.accent, transparent: true, opacity: 0.95, depthWrite: false }),
  )
  doneTubeGeo.setDrawRange(0, 0)
  world.add(baseTube, doneTube)

  const glow = glowTexture()
  const nodes: StageNode[] = STAGE_ORDER.map((id, i) => {
    const group = new THREE.Group()
    group.position.copy(orbit.getPointAt(i / 4))
    const mat = new THREE.MeshStandardMaterial({
      color: 0x232c42,
      emissive: COLOR.idle,
      emissiveIntensity: 0.25,
      roughness: 0.3,
      metalness: 0.4,
    })
    const ball = new THREE.Mesh(new THREE.SphereGeometry(0.36, 32, 24), mat)
    const halo = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: glow,
        color: COLOR.idle,
        transparent: true,
        opacity: 0.35,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    )
    halo.scale.setScalar(2.4)
    const label = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: labelTexture(STAGE_LABEL[id]),
        transparent: true,
        depthTest: false,
        depthWrite: false,
      }),
    )
    label.scale.set(2.4, 0.6, 1)
    label.position.set(0, 0.95, 0)
    label.renderOrder = 10
    group.add(halo, ball, label)
    world.add(group)
    return { id, group, mat, halo, state: 'pending', flash: 0 }
  })

  const packetMat = new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xffffff, emissiveIntensity: 0.9 })
  const packet = new THREE.Mesh(new THREE.OctahedronGeometry(0.2, 0), packetMat)
  const packetGlow = new THREE.Sprite(
    new THREE.SpriteMaterial({
      map: glow,
      color: COLOR.accent,
      transparent: true,
      opacity: 0.9,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    }),
  )
  packetGlow.scale.setScalar(1.6)
  packet.add(packetGlow)
  world.add(packet)
  const trail = Array.from({ length: 9 }, (_, i) => {
    const sprite = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: glow,
        color: COLOR.accent,
        transparent: true,
        opacity: 0.5 * (1 - i / 9),
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    )
    sprite.scale.setScalar(0.7 * (1 - i / 12))
    world.add(sprite)
    return sprite
  })

  const shock = new THREE.Mesh(
    new THREE.TorusGeometry(1, 0.02, 8, 120),
    new THREE.MeshBasicMaterial({ color: COLOR.accent, transparent: true, opacity: 0, depthWrite: false }),
  )
  shock.rotation.x = Math.PI / 2.2
  world.add(shock)

  const dustCount = window.innerWidth < 700 ? 500 : 1200
  const positions = new Float32Array(dustCount * 3)
  for (let i = 0; i < dustCount; i++) {
    const r = 9 + Math.random() * 24
    const theta = Math.random() * Math.PI * 2
    const phi = Math.acos(2 * Math.random() - 1)
    positions.set(
      [r * Math.sin(phi) * Math.cos(theta), r * Math.sin(phi) * Math.sin(theta) * 0.7, r * Math.cos(phi) - 6],
      i * 3,
    )
  }
  const dustGeo = new THREE.BufferGeometry()
  dustGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  const dust = new THREE.Points(
    dustGeo,
    new THREE.PointsMaterial({
      color: COLOR.dust,
      size: 0.06,
      sizeAttenuation: true,
      transparent: true,
      opacity: 0.55,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    }),
  )
  scene.add(dust)

  let mode: SceneMode = 'idle'
  let focus: SceneFocus = 'hero'
  let speed = 0.25
  let packetPos = 0
  let packetTarget = 0
  let traveled = 0
  let shockT = -1
  let shake = 0
  let time = 0
  let width = 0
  let height = 0
  let stopped = false
  const pointer = { x: 0, y: 0 }
  const modeSpeed: Record<SceneMode, number> = { idle: 0.25, working: 1.2, done: 0.45, error: 0.08 }

  function applyNodeState(node: StageNode, state: StageState) {
    node.state = state
    node.flash = 1
  }

  function layoutTargets() {
    const aspect = width / Math.max(1, height)
    const visH = 2 * Math.tan((camera.fov * Math.PI) / 360) * camera.position.z
    const visW = visH * aspect
    const wide = aspect >= 1.25
    const heroScale = Math.min(1, (wide ? visW * 0.46 : visW * 0.88) / 14)
    const hero = wide ? { x: visW * 0.26, y: 0.05, s: heroScale } : { x: 0, y: visH * 0.28, s: heroScale }
    const results = wide
      ? { x: visW * 0.36, y: visH * 0.33, s: heroScale * 0.48 }
      : { x: 0, y: visH * 0.41, s: heroScale * 0.52 }
    return { hero, results }
  }

  function resize() {
    const w = canvas.clientWidth || window.innerWidth
    const h = canvas.clientHeight || window.innerHeight
    if (w === width && h === height) return
    width = w
    height = h
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
    renderer.setSize(w, h, false)
    camera.aspect = w / h
    camera.updateProjectionMatrix()
  }

  const onPointerMove = (event: PointerEvent) => {
    pointer.x = (event.clientX / window.innerWidth) * 2 - 1
    pointer.y = (event.clientY / window.innerHeight) * 2 - 1
  }
  const onContextLost = (event: Event) => {
    event.preventDefault()
    stopped = true
    renderer.setAnimationLoop(null)
    canvas.hidden = true
  }
  window.addEventListener('pointermove', onPointerMove, { passive: true })
  window.addEventListener('resize', resize)
  canvas.addEventListener('webglcontextlost', onContextLost)

  let last = performance.now()
  function tick(now: number) {
    if (stopped) return
    const dt = Math.min(0.05, (now - last) / 1000)
    last = now
    time += dt
    const calm = reduceMotion.matches
    const motion = calm ? 0.15 : 1
    resize()

    speed = damp(speed, modeSpeed[mode] * motion, 2.5, dt)
    core.rotation.y += dt * speed * 0.55
    core.rotation.x += dt * speed * 0.2
    wire.rotation.y -= dt * speed * 0.35
    wire2.rotation.z += dt * speed * 0.25
    rings[0].rotation.z += dt * speed * 0.6
    rings[1].rotation.z -= dt * speed * 0.45
    dust.rotation.y += dt * 0.012 * motion

    const pulse =
      mode === 'working' ? 0.5 + Math.sin(time * 4) * 0.2 : mode === 'done' ? 0.55 + Math.sin(time * 1.6) * 0.1 : 0.28
    const coreColor = mode === 'error' ? COLOR.error : mode === 'done' ? COLOR.guide : COLOR.accent
    solidMat.emissive.lerp(coreColor, 1 - Math.exp(-4 * dt))
    wireMat.color.lerp(coreColor, 1 - Math.exp(-4 * dt))
    solidMat.emissiveIntensity = damp(solidMat.emissiveIntensity, pulse, 6, dt)

    shake = damp(shake, 0, 3, dt)
    core.position.x = calm ? 0 : Math.sin(time * 60) * 0.14 * shake

    packetPos = damp(packetPos, packetTarget, calm ? 8 : 2.2, dt)
    const p = ((packetPos % 1) + 1) % 1
    packet.position.copy(orbit.getPointAt(packetTarget >= 1 && packetPos > 0.999 ? 0 : p))
    packet.rotation.x += dt * 2.2
    packet.rotation.y += dt * 1.7
    packetMat.emissive.lerp(mode === 'error' ? COLOR.error : COLOR.accent, 1 - Math.exp(-6 * dt))
    packetGlow.material.color.copy(packetMat.emissive)
    trail.forEach((sprite, i) => {
      const tp = (((packetPos - (i + 1) * 0.011) % 1) + 1) % 1
      sprite.position.copy(orbit.getPointAt(packetPos > 0.012 ? tp : 0))
      sprite.visible = packetPos > (i + 1) * 0.011 && Math.abs(packetPos - packetTarget) > 0.004
    })

    traveled = damp(traveled, Math.min(packetPos, 1), 12, dt)
    doneTubeGeo.setDrawRange(0, Math.floor(Math.min(1, traveled) * TUBE_SEGMENTS) * RADIAL * 6)

    nodes.forEach((node, i) => {
      node.flash = damp(node.flash, 0, 2.5, dt)
      const target = node.state === 'pending' ? COLOR.idle : node.state === 'error' ? COLOR.error : COLOR[node.id]
      node.mat.emissive.lerp(target, 1 - Math.exp(-6 * dt))
      node.halo.material.color.lerp(target, 1 - Math.exp(-6 * dt))
      const beat = node.state === 'active' ? 0.75 + Math.sin(time * 6) * 0.25 : node.state === 'done' ? 0.9 : 0.2
      node.mat.emissiveIntensity = damp(node.mat.emissiveIntensity, beat + node.flash * 0.6, 8, dt)
      const haloTarget =
        node.state === 'pending' ? 0.3 : node.state === 'active' ? 0.75 + Math.sin(time * 6) * 0.15 : 0.7
      node.halo.material.opacity = damp(node.halo.material.opacity, haloTarget, 6, dt)
      const grow = node.state === 'active' ? 1.25 : 1
      node.group.scale.setScalar(damp(node.group.scale.x, grow, 6, dt))
      node.group.position.y += Math.sin(time * 1.4 + i) * 0.0009 * motion
    })

    if (shockT >= 0 && !calm) {
      shockT += dt
      const k = shockT / 1.6
      shock.scale.setScalar(1 + k * 6)
      shock.material.opacity = Math.max(0, 0.7 * (1 - k))
      if (k >= 1) shockT = -1
    } else {
      shock.material.opacity = 0
    }

    const tgt = layoutTargets()[focus]
    const rate = calm ? 10 : 3.2
    world.position.x = damp(world.position.x, tgt.x, rate, dt)
    world.position.y = damp(world.position.y, tgt.y, rate, dt)
    world.scale.setScalar(damp(world.scale.x, tgt.s, rate, dt))
    world.rotation.y = calm ? 0 : Math.sin(time * 0.18) * 0.12

    camera.position.x = damp(camera.position.x, calm ? 0 : pointer.x * 1.1, 3, dt)
    camera.position.y = damp(camera.position.y, calm ? 0.8 : 0.8 - pointer.y * 0.7, 3, dt)
    camera.lookAt(0, 0, 0)
    renderer.render(scene, camera)
  }

  resize()
  renderer.setAnimationLoop(tick)

  return {
    setStage(stage, state) {
      const i = STAGE_ORDER.indexOf(stage)
      if (i < 0) return
      applyNodeState(nodes[i], state)
      if (state === 'error') shake = 1
      if (state === 'active') packetTarget = i / 4
      if (state === 'done') {
        packetTarget = i / 4
        if (i === STAGE_ORDER.length - 1) {
          packetTarget = 1
          shockT = 0
        }
      }
    },
    setMode(next) {
      mode = next
    },
    setFocus(next) {
      focus = next
    },
    reset() {
      nodes.forEach((node) => applyNodeState(node, 'pending'))
      packetTarget = 0
      packetPos = 0
      traveled = 0
      shockT = -1
      mode = 'idle'
    },
    dispose() {
      stopped = true
      renderer.setAnimationLoop(null)
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('resize', resize)
      canvas.removeEventListener('webglcontextlost', onContextLost)
      disposeScene(scene)
      renderer.dispose()
    },
  }
}
