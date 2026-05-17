<template>
  <div class="viewer-layout">
    <!-- Left: Document -->
    <div class="doc-pane" :style="{ width: paneLeft + '%' }">
      <div class="doc-toolbar">
        <a-button type="text" size="small" @click="router.back()" class="toolbar-btn">
          <arrow-left-outlined /> 返回
        </a-button>
        <span class="doc-filename">{{ docInfo?.filename || '加载中…' }}</span>
        <div v-if="docInfo?.file_type === 'pdf'" class="page-nav">
          <a-button type="text" size="small" :disabled="currentPage <= 0" @click="goToPage(currentPage - 1)">
            <left-outlined />
          </a-button>
          <span class="page-indicator">{{ currentPage + 1 }} / {{ numPages || '—' }}</span>
          <a-button type="text" size="small" :disabled="currentPage >= numPages - 1" @click="goToPage(currentPage + 1)">
            <right-outlined />
          </a-button>
        </div>
        <span v-else-if="docInfo?.file_type === 'docx'" class="doc-type-tag">Word 文档</span>
      </div>
      <div class="doc-viewport" ref="viewportRef" @scroll="onScroll">
        <!-- PDF rendering -->
        <div v-if="docInfo?.file_type === 'pdf'" class="pages-container">
          <canvas
            v-for="p in numPages"
            :key="p"
            :ref="(el) => setCanvasRef(el, p - 1)"
            class="pdf-canvas"
          />
        </div>
        <!-- Word HTML rendering -->
        <div v-else-if="wordHtml" class="word-content" v-html="wordHtml"></div>
        <!-- Placeholder -->
        <div v-else class="doc-placeholder">
          <div class="placeholder-icon">
            <file-text-outlined style="font-size: 40px; opacity: 0.4" />
          </div>
          <p v-if="docInfo && docInfo.file_type !== 'pdf' && docInfo.file_type !== 'docx'">
            {{ docInfo.file_type?.toUpperCase() }} 文档暂不支持在线预览
          </p>
          <p v-else>正在加载文档…</p>
        </div>
      </div>
    </div>

    <!-- Resize Handle -->
    <div class="resize-handle" @mousedown="startResize"></div>

    <!-- Right: Chunks -->
    <div class="chunk-pane" :style="{ width: 100 - paneLeft + '%' }">
      <div class="chunk-scroll">
        <div class="chunk-pane-header">
          <span class="page-label">{{ docInfo?.file_type === 'pdf' ? `第 ${currentPage + 1} 页` : '全部分块' }}</span>
          <span class="chunk-count">{{ displayChunks.length }} 个分块</span>
        </div>

        <a-spin :spinning="loading">
          <div v-if="displayChunks.length === 0 && !loading" class="empty-state">
            <span>暂无分块</span>
          </div>

          <div v-else class="chunk-groups">
            <div
              v-for="group in displayGroups"
              :key="group.key"
              class="chunk-group"
            >
              <div v-if="group.groupId" class="group-banner">
                <span class="group-label">关联组</span>
                <span class="group-id">{{ group.groupId }}</span>
                <span class="group-size">{{ group.chunks.length }} 个分块</span>
              </div>

              <div class="chunk-cards">
                <div
                  v-for="chunk in group.chunks"
                  :key="chunk.chunk_id"
                  :class="['chunk-card', { expanded: expandedId === chunk.chunk_id }]"
                  @click="toggleExpand(chunk.chunk_id)"
                >
                  <div class="card-head">
                    <span class="card-id">{{ chunk.chunk_id }}</span>
                    <span class="card-meta">{{ chunk.char_count }} 字</span>
                    <span :class="['card-type', `type-${chunk.chunk_type}`]">{{ chunk.chunk_type }}</span>
                  </div>

                  <!-- Expanded: full text + images -->
                  <template v-if="expandedId === chunk.chunk_id">
                    <div v-if="detailCache[chunk.chunk_id]" class="card-body">
                      <div class="full-text markdown-body" v-html="renderMarkdown(detailCache[chunk.chunk_id].full_text)"></div>
                      <div v-if="detailCache[chunk.chunk_id].image_urls.length" class="card-images" @click.stop>
                        <a-image
                          v-for="(url, i) in detailCache[chunk.chunk_id].image_urls"
                          :key="i"
                          :src="url"
                          :width="260"
                          :alt="'图片 ' + (i + 1)"
                        />
                      </div>
                    </div>
                    <div v-else class="card-loading">加载中…</div>
                  </template>

                  <!-- Collapsed: preview + image thumbnails -->
                  <template v-else>
                    <div class="card-preview">{{ chunk.full_text }}</div>
                    <div v-if="chunk.image_urls.length" class="card-thumbs">
                      <img
                        v-for="(url, i) in chunk.image_urls.slice(0, 3)"
                        :key="i"
                        :src="`/api/v1/images/${url}`"
                        class="thumb"
                        alt="缩略图"
                      />
                      <span v-if="chunk.image_urls.length > 3" class="thumb-more">+{{ chunk.image_urls.length - 3 }}</span>
                    </div>
                  </template>
                </div>
              </div>
            </div>
          </div>
        </a-spin>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { listChunks, getChunkDetail, type ChunkListItem, type ChunkDetail } from '@/api/chunks'
import { getDocumentStatus, type DocumentStatusResponse } from '@/api/documents'
import { renderMarkdown } from '@/utils/markdown'
import {
  ArrowLeftOutlined,
  LeftOutlined,
  RightOutlined,
  FileTextOutlined,
} from '@ant-design/icons-vue'
import * as pdfjsLib from 'pdfjs-dist'
import mammoth from 'mammoth/mammoth.browser.js'

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.mjs',
  import.meta.url,
).toString()

const router = useRouter()
const route = useRoute()
const docId = route.params.docId as string

const docInfo = ref<DocumentStatusResponse | null>(null)
const allChunks = ref<ChunkListItem[]>([])
const loading = ref(false)
const currentPage = ref(0)
const numPages = ref(0)
const paneLeft = ref(55)
const expandedId = ref<string | null>(null)
const viewportRef = ref<HTMLElement | null>(null)
const detailCache = ref<Record<string, ChunkDetail>>({})
const wordHtml = ref('')

const canvasRefs: (HTMLCanvasElement | null)[] = []
const pageHeights: number[] = []

let pdfDoc: pdfjsLib.PDFDocumentProxy | null = null
let resizing = false
let startX = 0
let startWidth = 0
let scrollTimer: ReturnType<typeof setTimeout> | null = null
let rendering = false

const pageChunks = computed(() => {
  return allChunks.value.filter((c) => c.page === currentPage.value)
})

// For Word docs show all chunks, for PDF show page-filtered
const displayChunks = computed(() => {
  if (docInfo.value?.file_type !== 'pdf') return allChunks.value
  return pageChunks.value
})

interface ChunkGroup {
  key: string
  groupId: string
  chunks: ChunkListItem[]
}

const displayGroups = computed<ChunkGroup[]>(() => {
  const chunks = displayChunks.value
  const groups: ChunkGroup[] = []
  const groupIdMap = new Map<string, ChunkListItem[]>()
  const usedIds = new Set<string>()

  // First pass: group by group_id
  for (const c of chunks) {
    if (c.group_id) {
      if (!groupIdMap.has(c.group_id)) groupIdMap.set(c.group_id, [])
      groupIdMap.get(c.group_id)!.push(c)
      usedIds.add(c.chunk_id)
    }
  }

  // Second pass: emit groups and standalone chunks in order
  const emitted = new Set<string>()
  for (const c of chunks) {
    if (emitted.has(c.chunk_id)) continue
    if (c.group_id && groupIdMap.has(c.group_id)) {
      const groupChunks = groupIdMap.get(c.group_id)!.sort((a, b) => a.chunk_index - b.chunk_index)
      groups.push({ key: c.group_id, groupId: c.group_id, chunks: groupChunks })
      groupChunks.forEach(gc => emitted.add(gc.chunk_id))
    } else {
      groups.push({ key: c.chunk_id, groupId: '', chunks: [c] })
      emitted.add(c.chunk_id)
    }
  }

  return groups
})

function setCanvasRef(el: unknown, index: number) {
  canvasRefs[index] = el as HTMLCanvasElement | null
}

async function fetchAllChunks() {
  const all: ChunkListItem[] = []
  let page = 1
  while (true) {
    const res = await listChunks(docId, { page, size: 100 })
    all.push(...res.items)
    if (all.length >= res.total) break
    page++
  }
  return all
}

async function fetchData() {
  loading.value = true
  try {
    const [doc, chunks] = await Promise.all([
      getDocumentStatus(docId),
      fetchAllChunks(),
    ])
    docInfo.value = doc
    allChunks.value = chunks

    if (doc.file_type === 'pdf') {
      await loadPdf()
    } else if (doc.file_type === 'docx') {
      await loadWord()
    }
  } catch (e: unknown) {
    message.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

async function loadPdf() {
  const url = `/api/v1/images/${docInfo.value!.raw_file_url}`
  const data = new Uint8Array(await (await fetch(url)).arrayBuffer())
  pdfDoc = await pdfjsLib.getDocument({ data }).promise
  numPages.value = pdfDoc.numPages
  await nextTick()
  await renderAllPages()
}

async function loadWord() {
  const url = `/api/v1/images/${docInfo.value!.raw_file_url}`
  const data = await (await fetch(url)).arrayBuffer()
  const result = await mammoth.convertToHtml({ arrayBuffer: data })
  wordHtml.value = result.value
}

async function renderAllPages() {
  if (!pdfDoc || rendering) return
  rendering = true
  try {
    const container = viewportRef.value
    if (!container) return
    const width = container.clientWidth - 20

    for (let i = 1; i <= numPages.value; i++) {
      const page = await pdfDoc.getPage(i)
      const viewport = page.getViewport({ scale: 1 })
      const scale = width / viewport.width
      const scaledViewport = page.getViewport({ scale })

      const canvas = canvasRefs[i - 1]
      if (!canvas) continue
      canvas.width = scaledViewport.width
      canvas.height = scaledViewport.height

      const ctx = canvas.getContext('2d')
      if (!ctx) continue
      await page.render({ canvasContext: ctx, viewport: scaledViewport }).promise

      pageHeights[i - 1] = scaledViewport.height
    }
  } finally {
    rendering = false
  }
}

function onScroll() {
  if (scrollTimer) clearTimeout(scrollTimer)
  scrollTimer = setTimeout(() => {
    const container = viewportRef.value
    if (!container || pageHeights.length === 0) return

    const scrollTop = container.scrollTop
    let accHeight = 0
    for (let i = 0; i < pageHeights.length; i++) {
      accHeight += pageHeights[i] + 8
      if (scrollTop < accHeight - container.clientHeight / 2) {
        currentPage.value = i
        return
      }
    }
    currentPage.value = pageHeights.length - 1
  }, 50)
}

function goToPage(page: number) {
  const container = viewportRef.value
  if (!container || page < 0 || page >= numPages.value) return

  let top = 0
  for (let i = 0; i < page; i++) {
    top += pageHeights[i] + 8
  }
  container.scrollTo({ top, behavior: 'smooth' })
  currentPage.value = page
}

async function toggleExpand(chunkId: string) {
  if (expandedId.value === chunkId) {
    expandedId.value = null
    return
  }
  expandedId.value = chunkId
  if (!detailCache.value[chunkId]) {
    try {
      detailCache.value[chunkId] = await getChunkDetail(chunkId)
    } catch {
      // detail fetch failed, show truncated text
    }
  }
}

// Resize
function startResize(e: MouseEvent) {
  resizing = true
  startX = e.clientX
  startWidth = paneLeft.value
  document.addEventListener('mousemove', doResize)
  document.addEventListener('mouseup', stopResize)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}

function doResize(e: MouseEvent) {
  if (!resizing) return
  const vw = window.innerWidth
  const delta = ((e.clientX - startX) / vw) * 100
  paneLeft.value = Math.min(80, Math.max(30, startWidth + delta))
}

function stopResize() {
  resizing = false
  document.removeEventListener('mousemove', doResize)
  document.removeEventListener('mouseup', stopResize)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}

// Re-render on pane resize
let resizeObserver: ResizeObserver | null = null
let rerenderTimer: ReturnType<typeof setTimeout> | null = null

onMounted(() => {
  fetchData()
  if (viewportRef.value) {
    resizeObserver = new ResizeObserver(() => {
      if (rerenderTimer) clearTimeout(rerenderTimer)
      rerenderTimer = setTimeout(() => renderAllPages(), 300)
    })
    resizeObserver.observe(viewportRef.value)
  }
})

onUnmounted(() => {
  stopResize()
  resizeObserver?.disconnect()
  if (scrollTimer) clearTimeout(scrollTimer)
  if (rerenderTimer) clearTimeout(rerenderTimer)
  pdfDoc?.destroy()
})
</script>

<style scoped>
.viewer-layout {
  display: flex;
  height: calc(100vh - var(--layout-header-height));
  overflow: hidden;
  background: var(--color-bg-base);
}

/* ── Left: Document ── */
.doc-pane {
  display: flex;
  flex-direction: column;
  min-width: 320px;
  background: var(--color-bg-elevated);
  border-right: 1px solid var(--color-border);
}

.doc-toolbar {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-4);
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}

.toolbar-btn {
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
}

.toolbar-btn:hover {
  color: var(--color-primary);
}

.doc-filename {
  flex: 1;
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.page-nav {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.page-indicator {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  font-variant-numeric: tabular-nums;
  min-width: 52px;
  text-align: center;
}

.doc-viewport {
  flex: 1;
  overflow-y: auto;
  background: #525659;
  padding: 10px;
}

.pages-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.pdf-canvas {
  display: block;
  max-width: 100%;
  background: white;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.word-content {
  padding: var(--space-6);
  background: white;
  color: var(--color-text-primary);
  font-size: var(--font-size-sm);
  line-height: 1.8;
  min-height: 100%;
}

.word-content table {
  border-collapse: collapse;
  width: 100%;
  margin: var(--space-3) 0;
}

.word-content td, .word-content th {
  border: 1px solid var(--color-border);
  padding: 6px 10px;
  font-size: var(--font-size-xs);
}

.word-content img {
  max-width: 100%;
}

.doc-type-tag {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  background: var(--color-bg-sunken);
  padding: 2px 8px;
  border-radius: var(--radius-full);
}

.doc-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: var(--space-4);
}

.placeholder-icon {
  width: 72px;
  height: 72px;
  border-radius: var(--radius-lg);
  background: rgba(255, 255, 255, 0.08);
  display: flex;
  align-items: center;
  justify-content: center;
}

.doc-placeholder p {
  font-size: var(--font-size-sm);
  color: rgba(255, 255, 255, 0.45);
}

/* ── Resize Handle ── */
.resize-handle {
  width: 6px;
  cursor: col-resize;
  background: transparent;
  position: relative;
  z-index: 10;
  flex-shrink: 0;
  transition: background var(--transition-fast);
}

.resize-handle:hover,
.resize-handle:active {
  background: var(--color-primary-border);
}

.resize-handle::after {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 2px;
  height: 28px;
  border-radius: 1px;
  background: var(--color-border-strong);
}

/* ── Right: Chunks ── */
.chunk-pane {
  display: flex;
  flex-direction: column;
  min-width: 280px;
}

.chunk-scroll {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-4) var(--space-5);
}

.chunk-pane-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.page-label {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--color-text-primary);
}

.chunk-count {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  background: var(--color-bg-sunken);
  padding: 2px 8px;
  border-radius: var(--radius-full);
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 120px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
}

/* ── Chunk Groups ── */
.chunk-groups {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.chunk-group {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.group-banner {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-3);
  background: var(--color-primary-bg);
  border-bottom: 1px solid var(--color-primary-border);
}

.group-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-primary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.group-id {
  font-size: var(--font-size-xs);
  font-family: 'SF Mono', 'Fira Code', monospace;
  color: var(--color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}

.group-size {
  font-size: 11px;
  color: var(--color-text-tertiary);
  flex-shrink: 0;
}

/* ── Chunk Cards ── */
.chunk-cards {
  display: flex;
  flex-direction: column;
}

.chunk-card {
  padding: var(--space-3);
  cursor: pointer;
  transition: background var(--transition-fast);
}

.chunk-card:not(:last-child) {
  border-bottom: 1px solid var(--color-border);
}

.chunk-card:hover {
  background: var(--color-bg-sunken);
}

.chunk-card.expanded {
  background: var(--color-primary-bg);
}

.card-head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
}

.card-id {
  font-size: var(--font-size-xs);
  font-family: 'SF Mono', 'Fira Code', monospace;
  color: var(--color-primary);
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}

.card-meta {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

.card-type {
  font-size: 11px;
  font-weight: 600;
  padding: 1px 7px;
  border-radius: var(--radius-full);
  text-transform: uppercase;
  letter-spacing: 0.03em;
  flex-shrink: 0;
}

.type-text { background: #dbeafe; color: #1e40af; }
.type-table { background: #fef3c7; color: #92400e; }
.type-mixed { background: #ede9fe; color: #5b21b6; }
.type-image { background: #fce7f3; color: #9d174d; }

.card-preview {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-thumbs {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-2);
  align-items: center;
}

.thumb {
  width: 48px;
  height: 48px;
  object-fit: cover;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border);
}

.thumb-more {
  font-size: 11px;
  color: var(--color-text-tertiary);
}

.card-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.full-text {
  font-size: var(--font-size-sm);
  line-height: 1.8;
}

.card-images {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.card-loading {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  padding: var(--space-2) 0;
}
</style>
