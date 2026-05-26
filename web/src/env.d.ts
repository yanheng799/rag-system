/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<object, object, unknown>
  export default component
}

declare module 'mammoth/mammoth.browser.js' {
  interface MammothOptions {
    arrayBuffer?: ArrayBuffer
  }
  const mammoth: {
    convertToHtml: (input: MammothOptions) => Promise<{ value: string }>
  }
  export default mammoth
}
