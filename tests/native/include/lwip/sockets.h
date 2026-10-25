// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <arpa/inet.h>
#include <cerrno>
#include <sys/socket.h>
#include <unistd.h>
inline int fail_socket_attempts = 0;
inline int test_socket_calls = 0;
inline int test_socket_closes = 0;
inline int test_close(int descriptor) {
  ++test_socket_closes;
  return close(descriptor);
}
inline int test_socket(int domain, int type, int protocol) {
  ++test_socket_calls;
  if (fail_socket_attempts > 0) {
    --fail_socket_attempts;
    errno = EMFILE;
    return -1;
  }
  return socket(domain, type, protocol);
}
#define socket test_socket
#define close test_close
