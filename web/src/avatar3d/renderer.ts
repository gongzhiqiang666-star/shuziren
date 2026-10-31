import {
  ACESFilmicToneMapping,
  AmbientLight,
  Box3,
  Color,
  DirectionalLight,
  Group,
  HemisphereLight,
  LoadingManager,
  Mesh,
  Object3D,
  PerspectiveCamera,
  Quaternion,
  Scene,
  SRGBColorSpace,
  Texture,
  Vector2,
  Vector3,
  WebGLRenderer,
} from 'three'
import type { BufferGeometry, Material } from 'three'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'

export type AvatarViseme = 'sil' | 'PP' | 'FF' | 'TH' | 'DD' | 'kk' | 'CH' | 'SS' | 'nn' | 'RR' | 'aa' | 'E' | 'ih' | 'oh' | 'ou'
export type AvatarVisemeWeights = Partial<Readonly<Record<AvatarViseme, number>>>
export type AvatarBackground = 'studio' | 'green' | 'transparent'

export interface AvatarCapabilities {
  fileName: string
  byteLength: number
  meshCount: number
  triangleCount: number
  vertexCount: number
  morphTargets: string[]
  mouthSupport: 'oculus' | 'arkit' | 'none'
  hasUsableMouthRig: boolean
  missingVisemes: AvatarViseme[]
  hasBlink: boolean
  warnings: string[]
}

export interface AvatarRenderMetrics {
  fps: number
  triangles: number
  drawCalls: number
  width: number
  height: number
  pixelRatio: number
}

export interface AvatarRendererOptions {
  background?: AvatarBackground
  onMetrics?: (metrics: AvatarRenderMetrics) => void
  onError?: (message: string) => void
}

type MorphBinding = { mesh: Mesh; index: number }
type JsonObject = Record<string, unknown>

const VISEMES: readonly AvatarViseme[] = ['sil', 'PP', 'FF', 'TH', 'DD', 'kk', 'CH', 'SS', 'nn', 'RR', 'aa', 'E', 'ih', 'oh', 'ou']
const MAX_FILE_BYTES = 80 * 1024 * 1024
const MAX_JSON_BYTES = 4 * 1024 * 1024
const MAX_TRIANGLES = 2_000_000
const MAX_VERTICES = 2_000_000
const MAX_MESHES = 128
const MAX_MORPH_TARGETS_PER_MESH = 128
const MAX_IMAGE_COUNT = 64
const MAX_EMBEDDED_IMAGE_BYTES = 72 * 1024 * 1024
const MAX_TEXTURE_EDGE = 8192
const MAX_TEXTURE_PIXELS = 100_000_000
const MAX_ACCESSOR_BYTES = 160 * 1024 * 1024
const FRAME_MS = 1000 / 30

// Decoders are deliberately not installed or fetched at run time. These
// extensions require a separate asset-preparation workflow in this build.
const UNSUPPORTED_EXTENSIONS = new Set(['KHR_draco_mesh_compression', 'EXT_meshopt_compression', 'KHR_texture_basisu', 'EXT_mesh_gpu_instancing'])

const VISEME_NAMES: Readonly<Record<AvatarViseme, readonly string[]>> = {
  sil: ['visemesil'], PP: ['visemepp'], FF: ['visemeff'], TH: ['visemeth'], DD: ['visemedd'],
  kk: ['visemekk'], CH: ['visemech'], SS: ['visemess'], nn: ['visemenn'], RR: ['visemerr'],
  aa: ['visemeaa'], E: ['visemee'], ih: ['visemeih', 'visemei'], oh: ['visemeoh', 'visemeo'], ou: ['visemeou', 'visemeu'],
}

function record(value: unknown): value is JsonObject {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function boundedInteger(value: unknown, minimum: number, maximum: number, label: string): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < minimum || value > maximum) {
    throw new Error(`${label}超出本地验证版的范围。`)
  }
  return value
}

function normalized(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]/g, '')
}

function weight(value: number | undefined): number {
  return typeof value === 'number' && Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 0
}

function assertSelfContained(value: unknown, depth = 0, budget = { count: 0 }): void {
  if (++budget.count > 100_000 || depth > 48) throw new Error('模型描述过于复杂，无法在本地验证版中加载。')
  if (Array.isArray(value)) {
    for (const child of value) assertSelfContained(child, depth + 1, budget)
  } else if (record(value)) {
    for (const [key, child] of Object.entries(value)) {
      if (key === 'uri') throw new Error('请使用资源全部内嵌的单文件 GLB；本版不会读取外部图片、缓冲区或网络地址。')
      if (UNSUPPORTED_EXTENSIONS.has(key)) throw new Error('此模型需要额外压缩解码器，请先导出未压缩、自包含的 GLB。')
      assertSelfContained(child, depth + 1, budget)
    }
  }
}

function imageDimensions(bytes: Uint8Array, mime: string): { width: number; height: number } {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  if (mime === 'image/png') {
    if (bytes.byteLength < 24 || view.getUint32(0) !== 0x89504e47 || view.getUint32(4) !== 0x0d0a1a0a || view.getUint32(12) !== 0x49484452) {
      throw new Error('模型包含无效 PNG 纹理。')
    }
    return { width: view.getUint32(16), height: view.getUint32(20) }
  }
  if (mime === 'image/jpeg') {
    if (bytes.length < 4 || bytes[0] !== 0xff || bytes[1] !== 0xd8) throw new Error('模型包含无效 JPEG 纹理。')
    let offset = 2
    while (offset + 4 <= bytes.length) {
      if (bytes[offset] !== 0xff) throw new Error('模型 JPEG 纹理头无效。')
      while (offset < bytes.length && bytes[offset] === 0xff) offset++
      const marker = bytes[offset++]
      if (marker === undefined || marker === 0xda || marker === 0xd9) break
      if (marker === 0x01 || (marker >= 0xd0 && marker <= 0xd7)) continue
      if (offset + 2 > bytes.length) break
      const size = view.getUint16(offset)
      if (size < 2 || offset + size > bytes.length) break
      if ([0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf].includes(marker)) {
        if (size < 8) break
        return { height: view.getUint16(offset + 3), width: view.getUint16(offset + 5) }
      }
      offset += size
    }
    throw new Error('无法读取模型 JPEG 纹理尺寸。')
  }
  if (mime === 'image/webp') {
    if (bytes.length < 30 || view.getUint32(0) !== 0x52494646 || view.getUint32(8) !== 0x57454250) throw new Error('模型包含无效 WebP 纹理。')
    const kind = view.getUint32(12)
    if (kind === 0x56503858) {
      const width = 1 + bytes[24]! + (bytes[25]! << 8) + (bytes[26]! << 16)
      const height = 1 + bytes[27]! + (bytes[28]! << 8) + (bytes[29]! << 16)
      return { width, height }
    }
    if (kind === 0x56503820 && bytes[23] === 0x9d && bytes[24] === 0x01 && bytes[25] === 0x2a) {
      return { width: view.getUint16(26, true) & 0x3fff, height: view.getUint16(28, true) & 0x3fff }
    }
    if (kind === 0x5650384c && bytes[20] === 0x2f) {
      const bits = view.getUint32(21, true)
      return { width: (bits & 0x3fff) + 1, height: ((bits >>> 14) & 0x3fff) + 1 }
    }
    throw new Error('不支持该 WebP 纹理编码，请导出 PNG 或 JPEG 纹理。')
  }
  throw new Error('模型纹理必须是内嵌 PNG、JPEG 或 WebP。')
}

/** Validate before asking WebGL/GLTFLoader to allocate model resources. */
export function validateAvatarGLB(buffer: ArrayBuffer): void {
  if (buffer.byteLength < 20 || buffer.byteLength > MAX_FILE_BYTES) throw new Error('GLB 文件须在 80 MiB 以内。')
  const view = new DataView(buffer)
  if (view.getUint32(0, true) !== 0x46546c67 || view.getUint32(4, true) !== 2 || view.getUint32(8, true) !== buffer.byteLength) {
    throw new Error('文件不是完整的 GLB 2.0 模型。')
  }
  let offset = 12
  let json: JsonObject | null = null
  let binary: Uint8Array | null = null
  while (offset < buffer.byteLength) {
    if (offset + 8 > buffer.byteLength) throw new Error('GLB 数据块不完整。')
    const length = view.getUint32(offset, true)
    const type = view.getUint32(offset + 4, true)
    offset += 8
    if (length % 4 !== 0 || offset + length > buffer.byteLength) throw new Error('GLB 数据块长度无效。')
    if (type === 0x4e4f534a && json === null && binary === null) {
      if (length < 2 || length > MAX_JSON_BYTES) throw new Error('GLB 模型描述大小超出范围。')
      let parsed: unknown
      try {
        parsed = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(new Uint8Array(buffer, offset, length)))
      } catch {
        throw new Error('GLB 模型描述不是有效的 JSON。')
      }
      if (!record(parsed)) throw new Error('GLB 模型描述必须是对象。')
      json = parsed
    } else if (type === 0x004e4942 && json !== null && binary === null) {
      binary = new Uint8Array(buffer, offset, length)
    } else {
      throw new Error('本版仅支持一个 JSON 描述和一个内嵌二进制数据块。')
    }
    offset += length
  }
  if (!json || !binary || !record(json.asset) || json.asset.version !== '2.0') throw new Error('GLB 缺少有效的模型或内嵌数据。')
  assertSelfContained(json)
  if (!Array.isArray(json.scenes) || json.scenes.length !== 1 || !record(json.scenes[0]) || (json.scene !== undefined && json.scene !== 0)) {
    throw new Error('本版请导出仅含一个场景的 GLB 人物。')
  }
  if (!Array.isArray(json.buffers) || json.buffers.length !== 1 || !record(json.buffers[0])) throw new Error('模型必须使用单个内嵌缓冲区。')
  const bufferLength = boundedInteger(json.buffers[0].byteLength, 1, binary.length, '缓冲区大小')
  if (binary.length - bufferLength > 3) throw new Error('GLB 缓冲区长度与内嵌数据不符。')
  const views = Array.isArray(json.bufferViews) ? json.bufferViews : []
  for (const entry of views) {
    if (!record(entry) || entry.buffer !== 0) throw new Error('模型缓冲视图无效。')
    const start = boundedInteger(entry.byteOffset ?? 0, 0, bufferLength, '缓冲偏移')
    const length = boundedInteger(entry.byteLength, 1, bufferLength, '缓冲长度')
    if (start + length > bufferLength) throw new Error('模型缓冲视图越界。')
  }
  const accessors = Array.isArray(json.accessors) ? json.accessors : []
  if (accessors.length > 8192) throw new Error('模型访问器过多。')
  const componentBytes: Readonly<Record<string, number>> = { 5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4 }
  const componentCounts: Readonly<Record<string, number>> = { SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4, MAT2: 4, MAT3: 9, MAT4: 16 }
  let accessorBytes = 0
  const checkRange = (viewIndex: unknown, byteOffset: unknown, length: number, label: string): { offset: number; dataView: JsonObject } => {
    const dataView = views[boundedInteger(viewIndex, 0, views.length - 1, label)]
    if (!record(dataView)) throw new Error('模型访问器引用无效。')
    const offset = boundedInteger(byteOffset ?? 0, 0, dataView.byteLength as number, label)
    if (offset + length > (dataView.byteLength as number)) throw new Error('模型访问器超出缓冲区。')
    return { offset: (dataView.byteOffset as number | undefined ?? 0) + offset, dataView }
  }
  for (const entry of accessors) {
    if (!record(entry)) throw new Error('模型访问器无效。')
    const count = boundedInteger(entry.count, 1, MAX_VERTICES * 3, '模型访问器计数')
    const bytesPerComponent = componentBytes[String(entry.componentType)]
    const components = componentCounts[String(entry.type)]
    if (!bytesPerComponent || !components) throw new Error('模型访问器类型无效。')
    accessorBytes += count * components * bytesPerComponent
    if (accessorBytes > MAX_ACCESSOR_BYTES) throw new Error('模型形变展开后超过 160 MiB，请减少顶点或形变数量。')
    const columns = entry.type === 'MAT2' ? 2 : entry.type === 'MAT3' ? 3 : entry.type === 'MAT4' ? 4 : 0
    const elementBytes = columns ? Math.ceil(columns * bytesPerComponent / 4) * 4 * columns : components * bytesPerComponent
    if (entry.bufferView !== undefined) {
      const baseView = views[boundedInteger(entry.bufferView, 0, views.length - 1, '访问器视图')]
      if (!record(baseView)) throw new Error('模型访问器视图无效。')
      const stride = baseView.byteStride === undefined ? elementBytes : boundedInteger(baseView.byteStride, elementBytes, 252, '顶点步长')
      checkRange(entry.bufferView, entry.byteOffset, (count - 1) * stride + elementBytes, '访问器范围')
    }
    if (entry.sparse !== undefined) {
      const sparse = entry.sparse
      if (!record(sparse) || !record(sparse.indices) || !record(sparse.values)) throw new Error('模型稀疏访问器无效。')
      const sparseCount = boundedInteger(sparse.count, 1, count, '稀疏顶点数量')
      const indexType = sparse.indices.componentType
      if (indexType !== 5121 && indexType !== 5123 && indexType !== 5125) throw new Error('模型稀疏索引类型无效。')
      const indexBytes = componentBytes[String(indexType)]!
      const indices = checkRange(sparse.indices.bufferView, sparse.indices.byteOffset, sparseCount * indexBytes, '稀疏索引范围')
      checkRange(sparse.values.bufferView, sparse.values.byteOffset, sparseCount * elementBytes, '稀疏数据范围')
      const binaryView = new DataView(binary.buffer, binary.byteOffset, binary.byteLength)
      let previous = -1
      for (let i = 0; i < sparseCount; i++) {
        const at = indices.offset + i * indexBytes
        const index = indexType === 5121 ? binaryView.getUint8(at) : indexType === 5123 ? binaryView.getUint16(at, true) : binaryView.getUint32(at, true)
        if (index <= previous || index >= count) throw new Error('模型稀疏索引必须递增且位于顶点范围内。')
        previous = index
      }
    }
  }
  const meshes = Array.isArray(json.meshes) ? json.meshes : []
  if (!meshes.length || meshes.length > MAX_MESHES) throw new Error('模型网格数量须为 1–128。')
  let vertices = 0
  let triangles = 0
  for (const mesh of meshes) {
    if (!record(mesh) || !Array.isArray(mesh.primitives) || mesh.primitives.length > 64) throw new Error('模型网格结构无效或过于复杂。')
    for (const primitive of mesh.primitives) {
      if (!record(primitive) || !record(primitive.attributes) || (primitive.mode !== undefined && primitive.mode !== 4)) throw new Error('本版只支持三角形人物网格。')
      const position = accessors[boundedInteger(primitive.attributes.POSITION, 0, accessors.length - 1, '顶点索引')]
      if (!record(position)) throw new Error('模型缺少顶点数据。')
      const count = boundedInteger(position.count, 1, MAX_VERTICES, '顶点数')
      vertices += count
      let indexCount = count
      if (primitive.indices !== undefined) {
        const indices = accessors[boundedInteger(primitive.indices, 0, accessors.length - 1, '三角形索引')]
        if (!record(indices)) throw new Error('模型三角形索引无效。')
        indexCount = boundedInteger(indices.count, 0, MAX_TRIANGLES * 3, '三角形数量')
      }
      triangles += Math.ceil(indexCount / 3)
      if (primitive.targets !== undefined && (!Array.isArray(primitive.targets) || primitive.targets.length > MAX_MORPH_TARGETS_PER_MESH)) throw new Error('单个网格的形变数量超出范围。')
    }
  }
  if (vertices > MAX_VERTICES || triangles > MAX_TRIANGLES) throw new Error('模型超过 200 万顶点或三角形；请先降低细节等级。')
  const images = Array.isArray(json.images) ? json.images : []
  if (images.length > MAX_IMAGE_COUNT) throw new Error('模型内嵌纹理超过 64 张。')
  let imageBytes = 0
  let imagePixels = 0
  for (const entry of images) {
    if (!record(entry) || typeof entry.mimeType !== 'string') throw new Error('模型纹理未指定有效编码。')
    const imageView = views[boundedInteger(entry.bufferView, 0, views.length - 1, '纹理索引')]
    if (!record(imageView)) throw new Error('模型纹理数据无效。')
    const start = boundedInteger(imageView.byteOffset ?? 0, 0, bufferLength, '纹理偏移')
    const length = boundedInteger(imageView.byteLength, 1, bufferLength, '纹理长度')
    imageBytes += length
    if (imageBytes > MAX_EMBEDDED_IMAGE_BYTES) throw new Error('模型内嵌纹理数据过大。')
    const dimensions = imageDimensions(binary.subarray(start, start + length), entry.mimeType)
    const width = boundedInteger(dimensions.width, 1, MAX_TEXTURE_EDGE, '纹理宽度')
    const height = boundedInteger(dimensions.height, 1, MAX_TEXTURE_EDGE, '纹理高度')
    imagePixels += width * height
    if (imagePixels > MAX_TEXTURE_PIXELS) throw new Error('模型纹理解码后过大，请降低纹理分辨率。')
  }
  const nodes = Array.isArray(json.nodes) ? json.nodes : []
  if (nodes.length > 4096) throw new Error('模型节点过多。')
  // Node cycles cause unbounded traversal in loaders, and repeated mesh nodes
  // would otherwise bypass the primitive budget above.
  const colors = new Uint8Array(nodes.length)
  const parents = new Uint8Array(nodes.length)
  const references = new Uint32Array(meshes.length)
  const visit = (index: number, depth: number): void => {
    if (depth > 96 || colors[index] === 1) throw new Error('模型节点存在循环或层次过深。')
    if (colors[index] === 2) return
    const node = nodes[index]
    if (!record(node)) throw new Error('模型节点无效。')
    colors[index] = 1
    if (node.mesh !== undefined) references[boundedInteger(node.mesh, 0, meshes.length - 1, '网格索引')]!++
    if (node.children !== undefined) {
      if (!Array.isArray(node.children)) throw new Error('模型子节点无效。')
      for (const child of node.children) {
        const childIndex = boundedInteger(child, 0, nodes.length - 1, '子节点索引')
        if (++parents[childIndex]! > 1) throw new Error('模型节点不能同时属于多个父节点。')
        visit(childIndex, depth + 1)
      }
    }
    colors[index] = 2
  }
  for (let i = 0; i < nodes.length; i++) visit(i, 0)
  if (!Array.isArray(json.scenes[0].nodes)) throw new Error('模型场景缺少根节点。')
  for (const root of json.scenes[0].nodes) {
    const index = boundedInteger(root, 0, nodes.length - 1, '场景根节点')
    if (++parents[index]! > 1) throw new Error('模型根节点不能重复或同时属于子节点。')
  }
  if ([...references].some(count => count > 8)) throw new Error('模型重复网格实例过多。')
}

function disposeObject(object: Object3D): void {
  const geometries = new Set<BufferGeometry>()
  const materials = new Set<Material>()
  const textures = new Set<Texture>()
  object.traverse(node => {
    if (!(node instanceof Mesh)) return
    geometries.add(node.geometry)
    for (const material of Array.isArray(node.material) ? node.material : [node.material]) {
      materials.add(material)
      for (const candidate of Object.values(material)) if (candidate instanceof Texture) textures.add(candidate)
    }
  })
  for (const texture of textures) {
    const image: unknown = texture.image
    texture.dispose()
    if (typeof ImageBitmap !== 'undefined' && image instanceof ImageBitmap) image.close()
  }
  for (const material of materials) material.dispose()
  for (const geometry of geometries) geometry.dispose()
}

/** A fixed resting pose for the explicitly recognized Mixamo arm chain only. */
function relaxRecognizedArms(model: Object3D): boolean {
  const bones = new Map<string, Object3D>()
  model.traverse(node => {
    if ('isBone' in node && node.isBone === true) bones.set(normalized(node.name).replace(/^mixamorig/, ''), node)
  })
  const down = new Vector3(0, -1, 0)
  let changed = false
  const aim = (bone: Object3D, child: Object3D, desired: Vector3): void => {
    model.updateMatrixWorld(true)
    const from = child.getWorldPosition(new Vector3()).sub(bone.getWorldPosition(new Vector3()))
    if (from.lengthSq() < 1e-10 || !bone.parent) return
    from.normalize()
    const worldRotation = bone.getWorldQuaternion(new Quaternion())
    const correction = new Quaternion().setFromUnitVectors(from, desired.normalize())
    const parentInverse = bone.parent.getWorldQuaternion(new Quaternion()).invert()
    bone.quaternion.copy(parentInverse.multiply(correction.multiply(worldRotation)))
    bone.updateMatrixWorld(true)
  }
  for (const side of ['left', 'right']) {
    const upper = bones.get(`${side}arm`)
    const fore = bones.get(`${side}forearm`)
    const hand = bones.get(`${side}hand`)
    // Twist/helper chains and arbitrary rigs are intentionally left untouched.
    if (!upper || !fore || !hand || fore.parent !== upper || hand.parent !== fore) continue
    model.updateMatrixWorld(true)
    const shoulder = upper.getWorldPosition(new Vector3())
    const current = fore.getWorldPosition(new Vector3()).sub(shoulder)
    if (current.lengthSq() < 1e-10 || current.normalize().dot(down) > 0.82) continue
    const sign = Math.sign(shoulder.x) || (side === 'left' ? 1 : -1)
    aim(upper, fore, new Vector3(sign * 0.16, -1, 0.04))
    aim(fore, hand, new Vector3(sign * 0.07, -1, 0.16))
    changed = true
  }
  model.updateMatrixWorld(true)
  return changed
}

/** Local-only GLB viewer. Audio scheduling belongs to the caller. */
export class AvatarRenderer {
  readonly canvas: HTMLCanvasElement
  private readonly renderer: WebGLRenderer
  private readonly scene = new Scene()
  private readonly camera = new PerspectiveCamera(32, 1, 0.01, 100)
  private readonly controls: OrbitControls
  private readonly observer: ResizeObserver
  private readonly options: AvatarRendererOptions
  private model: Group | null = null
  private bindings = new Map<string, MorphBinding[]>()
  private head: Object3D | null = null
  private headInitial = { x: 0, y: 0, z: 0 }
  private disposed = false
  private loadGeneration = 0
  private frame = 0
  private lastFrameAt = 0
  private metricsAt = 0
  private metricsFrames = 0
  private motionEnabled = true
  private background: AvatarBackground
  private modelHeight = 1.8
  private weights: AvatarVisemeWeights = { sil: 1 }
  private renderable = true

  constructor(private readonly container: HTMLElement, options: AvatarRendererOptions = {}) {
    this.options = options
    this.background = options.background ?? 'studio'
    this.renderer = new WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'low-power' })
    this.renderer.outputColorSpace = SRGBColorSpace
    this.renderer.toneMapping = ACESFilmicToneMapping
    this.renderer.toneMappingExposure = 1.12
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5))
    this.canvas = this.renderer.domElement
    this.canvas.style.display = 'block'
    this.canvas.style.width = '100%'
    this.canvas.style.height = '100%'
    this.canvas.setAttribute('aria-label', '本地三维人物，可拖动旋转并滚轮缩放')
    container.appendChild(this.canvas)
    this.controls = new OrbitControls(this.camera, this.canvas)
    this.controls.enableDamping = true
    this.controls.dampingFactor = 0.12
    this.controls.minDistance = 0.3
    this.controls.maxDistance = 8
    this.controls.maxPolarAngle = Math.PI * 0.95
    this.controls.enablePan = true
    this.scene.add(new HemisphereLight(0xe9f2ff, 0x51566a, 2.1))
    this.scene.add(new AmbientLight(0xffffff, 0.45))
    const key = new DirectionalLight(0xfff2e6, 2.4)
    key.position.set(2, 3, 4)
    this.scene.add(key)
    const fill = new DirectionalLight(0xcfe0ff, 1.15)
    fill.position.set(-3, 1.8, 2)
    this.scene.add(fill)
    const rim = new DirectionalLight(0xffffff, 1.3)
    rim.position.set(-1, 3, -2)
    this.scene.add(rim)
    this.setBackground(this.background)
    this.resetCamera()
    this.observer = new ResizeObserver(() => this.resize())
    this.observer.observe(container)
    this.canvas.addEventListener('webglcontextlost', this.handleContextLost)
    this.canvas.addEventListener('webglcontextrestored', this.handleContextRestored)
    this.resize()
    this.frame = requestAnimationFrame(this.tick)
  }

  private readonly handleContextLost = (event: Event): void => {
    event.preventDefault()
    this.renderable = false
    this.options.onError?.('浏览器图形上下文已中断；暂停播放并重新加载人物。')
  }

  private readonly handleContextRestored = (): void => {
    if (!this.disposed) this.renderable = true
  }

  private resize(): void {
    if (this.disposed) return
    const width = Math.max(1, Math.min(1920, this.container.clientWidth))
    const height = Math.max(1, Math.min(1920, this.container.clientHeight))
    this.renderer.setSize(width, height, false)
    this.camera.aspect = width / height
    this.camera.updateProjectionMatrix()
  }

  async loadGLB(file: File): Promise<AvatarCapabilities> {
    if (this.disposed) throw new Error('三维预览已经关闭。')
    if (this.renderer.getContext().isContextLost()) throw new Error('浏览器图形上下文尚未恢复，请稍后重试或重新打开页面。')
    if (file.size < 20 || file.size > MAX_FILE_BYTES) throw new Error('请选取不超过 80 MiB 的自包含 GLB 文件。')
    const generation = ++this.loadGeneration
    const bytes = await file.arrayBuffer()
    if (this.disposed || generation !== this.loadGeneration) throw new Error('人物加载已取消。')
    validateAvatarGLB(bytes)
    const manager = new LoadingManager()
    manager.setURLModifier(url => {
      if (!url.startsWith('blob:')) throw new Error('禁止从模型加载外部资源。')
      return url
    })
    const loader = new GLTFLoader(manager)
    const gltf = await loader.parseAsync(bytes, '')
    if (this.disposed || generation !== this.loadGeneration) {
      disposeObject(gltf.scene)
      throw new Error('人物加载已取消。')
    }
    const wrapper = new Group()
    wrapper.add(gltf.scene)
    try {
      const box = new Box3().setFromObject(wrapper)
      const size = box.getSize(new Vector3())
      const center = box.getCenter(new Vector3())
      if (![size.x, size.y, size.z, center.x, center.y, center.z].every(Number.isFinite) || size.y <= 0.00001 || size.y > 10000) {
        throw new Error('人物模型的尺寸或坐标无效。')
      }
      const scale = 1.8 / size.y
      gltf.scene.position.add(new Vector3(-center.x, -box.min.y, -center.z))
      wrapper.scale.setScalar(scale)
      wrapper.updateMatrixWorld(true)
      const restingPose = relaxRecognizedArms(wrapper)
      const capability = this.inspectModel(wrapper, file)
      if (restingPose) capability.warnings.push('已为识别出的 Mixamo 手臂设置固定下垂待机姿势；不包含动态手势。')
      if (capability.meshCount > MAX_MESHES || capability.triangleCount > MAX_TRIANGLES || capability.vertexCount > MAX_VERTICES) {
        throw new Error('人物实际实例数量超过本版的渲染预算。')
      }
      this.releaseCurrentModel()
      this.model = wrapper
      this.modelHeight = 1.8
      this.scene.add(wrapper)
      this.collectBindings(wrapper)
      this.weights = { sil: 1 }
      this.applyMouth()
      this.resetCamera()
      if (this.renderer.getContext().isContextLost()) throw new Error('加载时浏览器图形上下文中断，请重新加载人物。')
      this.renderable = true
      return capability
    } catch (error) {
      if (this.model === wrapper) this.releaseCurrentModel()
      else disposeObject(wrapper)
      throw error
    }
  }

  private inspectModel(model: Object3D, file: File): AvatarCapabilities {
    const names = new Set<string>()
    let meshCount = 0
    let triangleCount = 0
    let vertexCount = 0
    model.traverse(node => {
      if (!(node instanceof Mesh)) return
      meshCount++
      const count = node.geometry.getAttribute('position')?.count ?? 0
      vertexCount += count
      triangleCount += Math.ceil((node.geometry.index?.count ?? count) / 3)
      for (const name of Object.keys(node.morphTargetDictionary ?? {})) names.add(name)
      // The workbench owns stage lighting. Embedded lights/shadows must not
      // silently multiply rendering cost or change comparison conditions.
      node.castShadow = false
      node.receiveShadow = false
    })
    const normalizedNames = new Set([...names].map(normalized))
    const hasViseme = (id: AvatarViseme): boolean => VISEME_NAMES[id].some(name => normalizedNames.has(name))
    // A neutral base mesh is the normal silent pose; a dedicated "sil" shape
    // is optional and must not make an otherwise valid Oculus rig fail.
    const missingVisemes = VISEMES.filter(id => id !== 'sil' && !hasViseme(id))
    const oculusCount = VISEMES.length - missingVisemes.length
    const arkit = ['jawopen', 'mouthclose', 'mouthfunnel', 'mouthpucker'].every(name => normalizedNames.has(name))
    const essential = ['PP', 'FF', 'aa', 'E', 'oh', 'ou'] as const
    const oculusUsable = essential.every(hasViseme)
    const mouthSupport = oculusCount > 1 ? 'oculus' : arkit ? 'arkit' : 'none'
    const warnings: string[] = []
    if (!oculusUsable && !arkit) warnings.push('缺少完整的基础嘴形；可查看模型，但不能据此验收口型。')
    if (oculusCount > 1 && missingVisemes.length) warnings.push(`缺少 ${missingVisemes.length} 种标准嘴形：${missingVisemes.join('、')}。`)
    if (mouthSupport === 'arkit') warnings.push('使用通用 ARKit 嘴形映射；中文闭唇、唇齿和连读仍需逐人物校准。')
    if (file.size > 24 * 1024 * 1024 || triangleCount > 250_000) warnings.push('人物资产较重，请以目标低配电脑的实际帧率和内存表现判断。')
    warnings.push('人物三维可转动只证明模型结构；真人感、音素准确度和 OBS 接收需另行验收。')
    return {
      fileName: file.name,
      byteLength: file.size,
      meshCount,
      triangleCount,
      vertexCount,
      morphTargets: [...names].sort(),
      mouthSupport,
      hasUsableMouthRig: oculusUsable || arkit,
      missingVisemes,
      hasBlink: ['eyeblinkleft', 'eyeblinkright', 'eyeblink', 'blink'].some(name => normalizedNames.has(name)),
      warnings,
    }
  }

  private collectBindings(model: Object3D): void {
    this.bindings.clear()
    this.head = null
    const lights: Object3D[] = []
    model.traverse(node => {
      if ('isLight' in node && node.isLight === true) lights.push(node)
      const boneName = normalized(node.name)
      if ('isBone' in node && node.isBone === true && ['head', 'mixamorighead', 'ccbasehead', 'bip01head'].includes(boneName)) this.head = node
      if (!(node instanceof Mesh) || !node.morphTargetInfluences) return
      for (const [name, index] of Object.entries(node.morphTargetDictionary ?? {})) {
        const key = normalized(name)
        const entries = this.bindings.get(key) ?? []
        entries.push({ mesh: node, index })
        this.bindings.set(key, entries)
      }
    })
    for (const light of lights) light.removeFromParent()
    if (this.head) {
      const head = this.head as Object3D
      this.headInitial = { x: head.rotation.x, y: head.rotation.y, z: head.rotation.z }
    }
  }

  setVisemes(weights: AvatarVisemeWeights): void {
    if (this.disposed) return
    // Copy a bounded set; callers may reuse their animation buffer afterward.
    this.weights = Object.fromEntries(VISEMES.map(id => [id, weight(weights[id])]))
    this.applyMouth()
  }

  private setMorph(name: string, amount: number): void {
    for (const binding of this.bindings.get(normalized(name)) ?? []) {
      if (binding.mesh.morphTargetInfluences) binding.mesh.morphTargetInfluences[binding.index] = weight(amount)
    }
  }

  private applyMouth(): void {
    for (const id of VISEMES) {
      for (const name of VISEME_NAMES[id]) this.setMorph(name, weight(this.weights[id]))
    }
    // Only use generic ARKit mapping when a mesh lacks Oculus viseme shapes;
    // using both on the same face would double-apply the deformation.
    const arkitWeights = this.arkitWeights()
    for (const [key, value] of Object.entries(arkitWeights)) {
      for (const binding of this.bindings.get(key) ?? []) {
        const dictionary = binding.mesh.morphTargetDictionary ?? {}
        if (Object.keys(dictionary).some(name => normalized(name) === 'visemeaa')) continue
        if (binding.mesh.morphTargetInfluences) binding.mesh.morphTargetInfluences[binding.index] = weight(value)
      }
    }
  }

  private arkitWeights(): Record<string, number> {
    const w = (id: AvatarViseme): number => weight(this.weights[id])
    const closed = Math.min(1, w('PP') + w('sil'))
    const jaw = (0.65 * w('aa') + 0.38 * w('E') + 0.23 * w('ih') + 0.28 * w('oh') + 0.15 * w('ou') + 0.14 * w('TH') + 0.12 * w('DD') + 0.13 * w('kk') + 0.08 * w('nn') + 0.12 * w('RR') + 0.07 * w('CH') + 0.04 * w('SS')) * (1 - closed)
    return {
      jawopen: jaw,
      mouthclose: w('PP'),
      mouthfunnel: 0.65 * w('oh') + 0.3 * w('ou') + 0.18 * w('CH'),
      mouthpucker: 0.7 * w('ou') + 0.2 * w('oh') + 0.12 * w('RR'),
      mouthsmileleft: 0.24 * w('E') + 0.16 * w('ih') + 0.1 * w('SS'),
      mouthsmileright: 0.24 * w('E') + 0.16 * w('ih') + 0.1 * w('SS'),
      mouthrolllower: 0.45 * w('FF'),
      mouthshruglower: 0.45 * w('FF'),
      mouthupperupleft: 0.18 * w('FF') + 0.12 * w('TH'),
      mouthupperupright: 0.18 * w('FF') + 0.12 * w('TH'),
      mouthlowerdownleft: 0.08 * w('aa') + 0.12 * w('TH'),
      mouthlowerdownright: 0.08 * w('aa') + 0.12 * w('TH'),
      tongueout: 0.12 * w('TH'),
    }
  }

  setIdleMotion(enabled: boolean): void {
    this.motionEnabled = enabled
    if (!enabled) {
      for (const key of ['eyeBlinkLeft', 'eyeBlinkRight', 'eyeBlink', 'blink']) this.setMorph(key, 0)
      if (this.head) this.head.rotation.set(this.headInitial.x, this.headInitial.y, this.headInitial.z)
    }
  }

  setBackground(mode: AvatarBackground): void {
    this.background = mode
    this.scene.background = mode === 'transparent' ? null : new Color(mode === 'green' ? '#00ff00' : '#172338')
    this.renderer.setClearColor(mode === 'green' ? 0x00ff00 : 0x172338, mode === 'transparent' ? 0 : 1)
  }

  resetCamera(): void {
    const targetY = this.modelHeight * 0.83
    this.controls.target.set(0, targetY, 0)
    this.camera.position.set(0, targetY + 0.02, 1.15)
    this.camera.lookAt(this.controls.target)
    this.controls.update()
  }

  private readonly tick = (now: number): void => {
    if (this.disposed) return
    this.frame = requestAnimationFrame(this.tick)
    if (!this.renderable || now - this.lastFrameAt < FRAME_MS - 1) return
    this.lastFrameAt = now
    if (this.motionEnabled && this.model) {
      const seconds = now / 1000
      // A deterministic, gentle blink. It never drives jaw or mouth targets.
      const cycle = seconds % 4.7
      const blink = cycle < 0.16 ? Math.sin(Math.PI * cycle / 0.16) : 0
      for (const key of ['eyeBlinkLeft', 'eyeBlinkRight', 'eyeBlink', 'blink']) this.setMorph(key, blink)
      if (this.head) {
        this.head.rotation.set(
          this.headInitial.x + Math.sin(seconds * 0.71) * 0.008,
          this.headInitial.y + Math.sin(seconds * 0.47) * 0.018,
          this.headInitial.z + Math.sin(seconds * 0.39) * 0.005,
        )
      }
    }
    this.controls.update()
    try {
      this.renderer.render(this.scene, this.camera)
    } catch {
      this.renderable = false
      this.options.onError?.('三维渲染失败，请暂停播放并重新加载人物；可尝试降低模型或纹理复杂度。')
      return
    }
    this.metricsFrames++
    if (this.metricsAt === 0) this.metricsAt = now
    if (now - this.metricsAt >= 1000) {
      const dimensions = this.renderer.getSize(new Vector2())
      this.options.onMetrics?.({
        fps: Math.round(this.metricsFrames * 10000 / (now - this.metricsAt)) / 10,
        triangles: this.renderer.info.render.triangles,
        drawCalls: this.renderer.info.render.calls,
        width: dimensions.x,
        height: dimensions.y,
        pixelRatio: this.renderer.getPixelRatio(),
      })
      this.metricsAt = now
      this.metricsFrames = 0
    }
  }

  private releaseCurrentModel(): void {
    if (this.model) {
      this.scene.remove(this.model)
      disposeObject(this.model)
    }
    this.model = null
    this.head = null
    this.bindings.clear()
  }

  clearModel(): void {
    this.loadGeneration++
    this.releaseCurrentModel()
    this.weights = { sil: 1 }
  }

  dispose(): void {
    if (this.disposed) return
    this.disposed = true
    this.loadGeneration++
    cancelAnimationFrame(this.frame)
    this.observer.disconnect()
    this.controls.dispose()
    this.canvas.removeEventListener('webglcontextlost', this.handleContextLost)
    this.canvas.removeEventListener('webglcontextrestored', this.handleContextRestored)
    this.releaseCurrentModel()
    this.renderer.dispose()
    this.renderer.forceContextLoss()
    this.canvas.remove()
  }
}
