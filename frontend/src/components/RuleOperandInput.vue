<script setup lang="ts">
import { operandOptions } from '@/api/strategyStudio'
import type { Operand, OperandKind } from '@/api/strategyStudio'
const props = defineProps<{ modelValue: Operand; label: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: Operand] }>()
function changeKind(event: Event): void {
  const kind = (event.target as HTMLSelectElement).value as OperandKind
  emit(
    'update:modelValue',
    kind === 'constant'
      ? { kind, value: 0 }
      : kind === 'external'
        ? { kind, factor: 'pe_ttm', maxAgeDays: 90 }
        : { kind, window: 20 },
  )
}
function update(key: string, event: Event, numeric = false): void {
  const value = (event.target as HTMLInputElement).value
  emit('update:modelValue', { ...props.modelValue, [key]: numeric ? Number(value) : value })
}
</script>
<template>
  <div class="operand-input">
    <select :value="modelValue.kind" :aria-label="`${label}类型`" @change="changeKind">
      <option v-for="item in operandOptions" :key="item.value" :value="item.value">
        {{ item.label }}
      </option>
    </select>
    <input
      v-if="modelValue.kind === 'constant'"
      type="number"
      step="any"
      :value="modelValue.value ?? 0"
      :aria-label="`${label}数值`"
      @input="update('value', $event, true)"
    />
    <template v-else-if="modelValue.kind === 'external'"
      ><input
        :value="modelValue.factor"
        :aria-label="`${label}因子名`"
        placeholder="如 pe_ttm"
        @input="update('factor', $event)" /><input
        type="number"
        min="1"
        max="366"
        :value="modelValue.maxAgeDays ?? 90"
        :aria-label="`${label}最长有效天数`"
        title="因子最长有效天数"
        @input="update('maxAgeDays', $event, true)"
    /></template>
    <input
      v-else-if="!['close', 'open', 'high', 'low', 'volume'].includes(modelValue.kind)"
      type="number"
      min="2"
      max="252"
      :value="modelValue.window ?? 20"
      :aria-label="`${label}窗口`"
      @input="update('window', $event, true)"
    />
  </div>
</template>
<style scoped>
.operand-input {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  min-width: 0;
}
select,
input {
  border: 1px solid #dce2eb;
  background: white;
  border-radius: 5px;
  padding: 7px;
  font-size: 11px;
  color: #475569;
  max-width: 100%;
  min-width: 0;
}
select {
  width: 125px;
}
input {
  width: 90px;
}
</style>
