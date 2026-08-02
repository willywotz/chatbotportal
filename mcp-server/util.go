package main

import (
	"crypto/rand"
	"encoding/hex"
	"log/slog"
	"time"
)

var bangkokLoc *time.Location

func init() {
	loc, err := time.LoadLocation("Asia/Bangkok")
	if err != nil {
		slog.Warn("Asia/Bangkok tzdata unavailable, falling back to UTC", slog.Any("error", err))
		loc = time.UTC
	}
	bangkokLoc = loc
}

func uuidV7() (string, error) {
	uuid, err := newUUIDv7()
	if err != nil {
		return "", err
	}
	return formatUUID(uuid), nil
}

func newUUIDv7() ([16]byte, error) {
	var uuid [16]byte
	ms := uint64(time.Now().UnixMilli())
	uuid[0] = byte(ms >> 40)
	uuid[1] = byte(ms >> 32)
	uuid[2] = byte(ms >> 24)
	uuid[3] = byte(ms >> 16)
	uuid[4] = byte(ms >> 8)
	uuid[5] = byte(ms)
	if _, err := rand.Read(uuid[6:]); err != nil {
		return uuid, err
	}
	uuid[6] = (uuid[6] & 0x0f) | 0x70
	uuid[8] = (uuid[8] & 0x3f) | 0x80
	return uuid, nil
}

func formatUUID(uuid [16]byte) string {
	var buf [36]byte
	hex.Encode(buf[0:8], uuid[0:4])
	buf[8] = '-'
	hex.Encode(buf[9:13], uuid[4:6])
	buf[13] = '-'
	hex.Encode(buf[14:18], uuid[6:8])
	buf[18] = '-'
	hex.Encode(buf[19:23], uuid[8:10])
	buf[23] = '-'
	hex.Encode(buf[24:36], uuid[10:16])
	return string(buf[:])
}

func now() time.Time {
	return time.Now().In(bangkokLoc)
}
