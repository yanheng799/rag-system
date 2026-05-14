import { Marked } from 'marked'
import DOMPurify from 'dompurify'

const marked = new Marked({
  gfm: true,
  breaks: true,
})

/**
 * 修复 markdown 表格中单元格内换行导致表格断裂的问题。
 * 对于连续以 | 开头的行（表格行），将不属于表格结构的换行（即不以 | 开头的行）
 * 合并到上一行并替换为 <br>。
 */
function fixTableNewlines(text: string): string {
  const lines = text.split('\n')
  const result: string[] = []

  for (const line of lines) {
    if (result.length > 0 && /^\|/.test(result[result.length - 1]) && !/^\|/.test(line)) {
      result[result.length - 1] += '<br>' + line
    } else {
      result.push(line)
    }
  }

  return result.join('\n')
}

export function renderMarkdown(text: string): string {
  const fixed = fixTableNewlines(text)
  const html = marked.parse(fixed) as string
  return DOMPurify.sanitize(html)
}
