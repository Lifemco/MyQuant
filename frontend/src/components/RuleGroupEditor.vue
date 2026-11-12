<script setup lang="ts">
import RuleOperandInput from './RuleOperandInput.vue'
import { constant } from '@/api/strategyStudio'
import type { Condition, Operand, RuleGroup } from '@/api/strategyStudio'
const props = defineProps<{ modelValue: RuleGroup; title: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: RuleGroup] }>()
function change(index: number, key: 'left' | 'right', value: Operand): void {
  emit('update:modelValue', {
    ...props.modelValue,
    conditions: props.modelValue.conditions.map((c, i) =>
      i === index ? { ...c, [key]: value } : c,
    ),
  })
}
function op(index: number, event: Event): void {
  const value = (event.target as HTMLSelectElement).value as Condition['op']
  emit('update:modelValue', {
    ...props.modelValue,
    conditions: props.modelValue.conditions.map((c, i) => (i === index ? { ...c, op: value } : c)),
  })
}
function remove(index: number): void {
  emit('update:modelValue', {
    ...props.modelValue,
    conditions: props.modelValue.conditions.filter((_, i) => i !== index),
  })
}
function add(): void {
  emit('update:modelValue', {
    ...props.modelValue,
    conditions: [
      ...props.modelValue.conditions,
      { left: { kind: 'close' }, op: 'gt', right: constant(0) },
    ],
  })
}
</script>
<template>
  <section class="rule-group">
    <div class="group-heading">
      <h3>{{ title }}</h3>
      <select
        :value="modelValue.logic"
        :aria-label="`${title}组合方式`"
        @change="
          emit('update:modelValue', {
            ...modelValue,
            logic: ($event.target as HTMLSelectElement).value as 'all' | 'any',
          })
        "
      >
        <option value="all">全部满足 AND</option>
        <option value="any">任一满足 OR</option>
      </select>
    </div>
    <div v-for="(condition, index) in modelValue.conditions" :key="index" class="condition-row">
      <RuleOperandInput
        :model-value="condition.left"
        :label="`${title}${index + 1}左侧`"
        @update:model-value="change(index, 'left', $event)"
      /><select
        :value="condition.op"
        :aria-label="`${title}${index + 1}比较`"
        @change="op(index, $event)"
      >
        <option value="gt">大于</option>
        <option value="gte">大于等于</option>
        <option value="lt">小于</option>
        <option value="lte">小于等于</option>
        <option value="cross_above">向上穿越</option>
        <option value="cross_below">向下穿越</option></select
      ><RuleOperandInput
        :model-value="condition.right"
        :label="`${title}${index + 1}右侧`"
        @update:model-value="change(index, 'right', $event)"
      /><button
        :disabled="modelValue.conditions.length <= 1"
        :aria-label="`删除${title}${index + 1}`"
        @click="remove(index)"
      >
        ×
      </button>
    </div>
    <button class="add-condition" :disabled="modelValue.conditions.length >= 12" @click="add">
      ＋ 添加{{ title }}
    </button>
  </section>
</template>
<style scoped>
.rule-group {
  border: 1px solid #e5eaf0;
  border-radius: 8px;
  padding: 14px;
  margin: 12px 0;
}
.group-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
}
h3 {
  font-size: 13px;
  font-weight: 600;
}
.condition-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 88px minmax(0, 1fr) 22px;
  gap: 7px;
  align-items: start;
  margin: 9px 0;
}
select {
  background: #fff;
  border: 1px solid #dce2eb;
  border-radius: 5px;
  padding: 7px 3px;
  color: #64748b;
  font-size: 11px;
  min-width: 0;
}
button {
  background: none;
  border: 0;
  color: #9aa4b3;
  cursor: pointer;
}
button:disabled {
  opacity: 0.35;
}
.add-condition {
  color: #d23a47;
  font-size: 11px;
  padding-top: 8px;
}
@media (max-width: 1100px) {
  .condition-row {
    grid-template-columns: 1fr 75px 1fr 16px;
  }
}
@media (max-width: 620px) {
  .condition-row {
    grid-template-columns: 1fr 75px;
    border-top: 1px dashed #edf0f4;
    padding-top: 10px;
  }
  .rule-group {
    padding: 10px;
  }
}
</style>
