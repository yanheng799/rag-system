<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <h2 class="page-title">分块检索</h2>
        <p class="page-subtitle">按向量、BM25 或混合模式检索文档分块</p>
      </div>
    </div>

    <div class="filter-bar">
      <a-select
        v-model:value="selectedDatasetIds"
        mode="multiple"
        placeholder="选择知识库（可选）"
        style="min-width: 240px"
        :options="datasetOptions"
        allow-clear
        :max-tag-count="2"
      />
      <a-select
        v-model:value="selectedDocIds"
        mode="multiple"
        placeholder="选择文档（可选）"
        style="min-width: 240px"
        :options="docOptions"
        allow-clear
        :max-tag-count="2"
        :disabled="docLoading"
      />
    </div>

    <div class="search-bar">
      <a-radio-group v-model:value="searchMode" button-style="solid" class="mode-group">
        <a-radio-button value="hybrid">混合检索</a-radio-button>
        <a-radio-button value="vector">向量检索</a-radio-button>
        <a-radio-button value="bm25">BM25</a-radio-button>
      </a-radio-group>
      <a-input-number v-model:value="topK" :min="1" :max="50" style="width: 100px" addon-before="Top" />
      <a-input
        v-model:value="question"
        placeholder="输入检索内容"
        @pressEnter="handleRetrieve"
        style="flex: 1"
        size="large"
      />
      <a-button type="primary" :loading="loading" @click="handleRetrieve" :disabled="!question.trim()" size="large">
        <search-outlined /> 检索
      </a-button>
    </div>

    <div v-if="result" class="result-meta">
      <span class="result-stat">
        <span class="result-value">{{ result.total_retrieved }}</span> 条结果
      </span>
      <span class="result-divider">·</span>
      <span>{{ searchMode }} 模式</span>
      <span class="result-divider">·</span>
      <span class="tabular-nums">耗时 {{ result.retrieval_ms.toFixed(0) }}ms</span>
    </div>

    <a-empty v-if="!loading && result && result.chunks.length === 0" description="未找到相关分块" />

    <div class="chunk-list">
      <a-card v-for="chunk in result?.chunks" :key="chunk.metadata.chunk_id" class="chunk-card" size="small">
        <template #title>
          <div class="chunk-card-title">
            <span class="rank-badge">#{{ chunk.rank }}</span>
            <span class="chunk-filename">{{ chunk.metadata.filename }}</span>
            <span class="chunk-meta">第 {{ chunk.metadata.page }} 页 · {{ chunk.metadata.char_count }} 字</span>
            <router-link :to="`/chunks/${chunk.metadata.chunk_id}`" class="detail-link">详情 →</router-link>
          </div>
        </template>
        <div class="chunk-scores">
          <a-tag v-if="chunk.scores.vector_score > 0">向量: {{ chunk.scores.vector_score.toFixed(4) }}</a-tag>
          <a-tag v-if="chunk.scores.bm25_score > 0">BM25: {{ chunk.scores.bm25_score.toFixed(4) }}</a-tag>
          <a-tag v-if="chunk.scores.rrf_score != null" color="green">RRF: {{ chunk.scores.rrf_score.toFixed(4) }}</a-tag>
        </div>
        <div
          class="chunk-text markdown-body"
          :class="{ collapsed: !expandedChunks.has(chunk.metadata.chunk_id) }"
          v-html="renderMarkdown(chunk.full_text)"
        ></div>
        <a-button
          v-if="chunk.full_text.length > 500"
          type="link"
          size="small"
          @click="toggleChunkExpand(chunk.metadata.chunk_id)"
        >
          {{ expandedChunks.has(chunk.metadata.chunk_id) ? '收起' : '展开全文' }}
        </a-button>
        <div v-if="chunk.image_urls && chunk.image_urls.length > 0" class="chunk-images">
          <a-image
            v-for="(url, i) in chunk.image_urls"
            :key="i"
            :src="url"
            :width="200"
            :alt="'表格截图 ' + (i + 1)"
          />
        </div>
      </a-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { useRouter, useRoute } from 'vue-router'
import { retrieveChunks, type RetrieveResponse } from '@/api/retrieve'
import { listDatasets, type DatasetResponse } from '@/api/datasets'
import { listDocuments, type DocumentListItem } from '@/api/documents'
import { renderMarkdown } from '@/utils/markdown'
import { SearchOutlined } from '@ant-design/icons-vue'

const router = useRouter()
const route = useRoute()

const question = ref('')
const searchMode = ref<'vector' | 'bm25' | 'hybrid'>('hybrid')
const topK = ref(10)
const loading = ref(false)
const result = ref<RetrieveResponse | null>(null)
const expandedChunks = ref(new Set<string>())

function toggleChunkExpand(chunkId: string) {
  if (expandedChunks.value.has(chunkId)) {
    expandedChunks.value.delete(chunkId)
  } else {
    expandedChunks.value.add(chunkId)
  }
}

const datasets = ref<DatasetResponse[]>([])
const selectedDatasetIds = ref<string[]>([])
const docs = ref<DocumentListItem[]>([])
const selectedDocIds = ref<string[]>([])
const docLoading = ref(false)

const datasetOptions = computed(() =>
  datasets.value.map((ds) => ({ label: ds.name, value: ds.dataset_id }))
)

const docOptions = computed(() =>
  docs.value.map((d) => ({ label: d.filename, value: d.doc_id }))
)

async function fetchDatasets() {
  try {
    const res = await listDatasets({ size: 100 })
    datasets.value = res.items
  } catch (e: unknown) {
    message.error((e as Error).message)
  }
}

async function fetchDocs() {
  if (selectedDatasetIds.value.length === 0) {
    docs.value = []
    return
  }
  docLoading.value = true
  try {
    const allDocs: DocumentListItem[] = []
    for (const dsId of selectedDatasetIds.value) {
      const res = await listDocuments({ dataset_id: dsId, size: 100 })
      allDocs.push(...res.items)
    }
    docs.value = allDocs
  } catch (e: unknown) {
    message.error((e as Error).message)
  } finally {
    docLoading.value = false
  }
}

watch(selectedDatasetIds, () => {
  selectedDocIds.value = []
  fetchDocs()
})

async function handleRetrieve() {
  const q = question.value.trim()
  if (!q || loading.value) return
  loading.value = true
  result.value = null
  try {
    result.value = await retrieveChunks({
      question: q,
      top_k: topK.value,
      search_mode: searchMode.value,
      dataset_ids: selectedDatasetIds.value.length > 0 ? selectedDatasetIds.value : undefined,
      doc_ids: selectedDocIds.value.length > 0 ? selectedDocIds.value : undefined,
    })
  } catch (e: unknown) {
    message.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

function parseUrlIds(param: string | string[] | undefined): string[] {
  if (!param) return []
  if (Array.isArray(param)) return param
  return [param]
}

onMounted(async () => {
  await fetchDatasets()

  const urlDatasetIds = parseUrlIds(route.query.dataset_ids as string | string[] | undefined)
  const urlDocIds = parseUrlIds(route.query.doc_ids as string | string[] | undefined)

  if (urlDatasetIds.length > 0) {
    selectedDatasetIds.value = urlDatasetIds
    await fetchDocs()
  }
  if (urlDocIds.length > 0) {
    selectedDocIds.value = urlDocIds
  }
})
</script>

<style scoped>
.page-container {
  padding: var(--space-8) var(--space-6);
  max-width: 1200px;
  margin: 0 auto;
}

.page-subtitle {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  margin-top: var(--space-1);
}

.filter-bar {
  display: flex;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.search-bar {
  display: flex;
  gap: var(--space-3);
  margin-bottom: var(--space-6);
  align-items: center;
}

.mode-group {
  flex-shrink: 0;
}

.result-meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-5);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  padding: var(--space-3) var(--space-4);
  background: var(--color-bg-elevated);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
}

.result-stat {
  font-weight: 500;
}

.result-value {
  color: var(--color-primary);
  font-weight: 700;
}

.result-divider {
  color: var(--color-text-tertiary);
}

.chunk-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.chunk-card {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg) !important;
  transition: all var(--transition-normal);
}

.chunk-card:hover {
  border-color: var(--color-primary-border);
  box-shadow: var(--shadow-sm);
}

.chunk-card-title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-sm);
}

.rank-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 22px;
  border-radius: var(--radius-sm);
  background: var(--color-primary);
  color: #ffffff;
  font-size: var(--font-size-xs);
  font-weight: 700;
}

.chunk-filename {
  font-weight: 500;
  color: var(--color-text-primary);
}

.chunk-meta {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
}

.detail-link {
  margin-left: auto;
  font-size: var(--font-size-xs);
  font-weight: 500;
  color: var(--color-primary);
  text-decoration: none;
  transition: opacity var(--transition-fast);
}

.detail-link:hover {
  opacity: 0.8;
}

.chunk-scores {
  margin-bottom: var(--space-2);
}

.chunk-text {
  line-height: 1.7;
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  overflow-y: auto;
}

.chunk-text.collapsed {
  max-height: 200px;
  overflow: hidden;
  position: relative;
}

.chunk-text.collapsed::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 48px;
  background: linear-gradient(transparent, var(--color-bg-elevated));
  pointer-events: none;
}

.chunk-images {
  margin-top: var(--space-3);
  display: flex;
  gap: var(--space-3);
}
</style>
