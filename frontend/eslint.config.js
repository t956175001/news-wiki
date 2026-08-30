import pluginVue from 'eslint-plugin-vue'
import { withVueTs, vueTsConfigs } from '@vue/eslint-config-typescript'
import prettierConfig from '@vue/eslint-config-prettier'

export default withVueTs(
  {
    name: 'app/files-to-lint',
    files: ['src/**/*.{ts,mts,tsx,vue}'],
  },
  {
    name: 'app/files-to-ignore',
    ignores: ['**/dist/**', '**/dist-ssr/**', '**/coverage/**'],
  },
  pluginVue.configs['flat/recommended'],
  vueTsConfigs.recommended,
  prettierConfig,
)
