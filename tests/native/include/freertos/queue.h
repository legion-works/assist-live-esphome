// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cassert>
#include <cstddef>
#include <cstring>
#include <deque>
#include <stdexcept>
#include <vector>
struct TestQueue {
  size_t capacity, size;
  std::deque<std::vector<char>> items;
};
using QueueHandle_t = TestQueue *;
inline bool fail_queue = false;
inline QueueHandle_t xQueueCreate(size_t capacity, size_t size) {
  return fail_queue ? nullptr : new TestQueue{capacity, size, {}};
}
inline void vQueueDelete(QueueHandle_t queue) { delete queue; }
inline int xQueueSend(QueueHandle_t queue, const void *event, int ticks) {
  assert(ticks == 0);
  if (queue->items.size() == queue->capacity)
    return 0;
  const auto *bytes = static_cast<const char *>(event);
  queue->items.emplace_back(bytes, bytes + queue->size);
  return 1;
}
inline int xQueueReceive(QueueHandle_t queue, void *event, int) {
  if (queue->items.empty())
    throw std::runtime_error("worker drained");
  std::memcpy(event, queue->items.front().data(), queue->size);
  queue->items.pop_front();
  return 1;
}
