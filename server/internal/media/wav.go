package media

import "encoding/binary"

// validateWAV bounds both memory and play time. The local worker emits this
// deliberately narrow format: RIFF/WAVE, mono PCM16, 8-48 kHz, <= 300 seconds.
// Metadata chunks are allowed; truncated chunks, duplicate audio chunks, float
// samples, inconsistent frame sizes, and compressed containers are rejected.
func validateWAV(wav []byte) error {
	if len(wav) < 44 || len(wav) > MaxAudioBytes || string(wav[:4]) != "RIFF" || string(wav[8:12]) != "WAVE" {
		return ErrInvalidInput
	}
	le := binary.LittleEndian
	if uint64(le.Uint32(wav[4:8]))+8 != uint64(len(wav)) {
		return ErrInvalidInput
	}
	var haveFormat, haveData bool
	var sampleRate, dataBytes uint32
	for offset := 12; offset < len(wav); {
		if len(wav)-offset < 8 {
			return ErrInvalidInput
		}
		kind := string(wav[offset : offset+4])
		size := uint64(le.Uint32(wav[offset+4 : offset+8]))
		start := offset + 8
		if size > uint64(len(wav)-start) {
			return ErrInvalidInput
		}
		end := start + int(size)
		switch kind {
		case "fmt ":
			if haveFormat || size < 16 {
				return ErrInvalidInput
			}
			haveFormat = true
			format := wav[start:end]
			sampleRate = le.Uint32(format[4:8])
			if le.Uint16(format[0:2]) != 1 || le.Uint16(format[2:4]) != 1 || sampleRate < 8000 || sampleRate > 48000 ||
				le.Uint16(format[12:14]) != 2 || le.Uint16(format[14:16]) != 16 || le.Uint32(format[8:12]) != sampleRate*2 {
				return ErrInvalidInput
			}
		case "data":
			if haveData || size == 0 || size%2 != 0 {
				return ErrInvalidInput
			}
			haveData = true
			dataBytes = uint32(size)
		}
		offset = end + int(size%2)
		if offset > len(wav) {
			return ErrInvalidInput
		}
	}
	if !haveFormat || !haveData || uint64(dataBytes) > uint64(sampleRate)*2*300 {
		return ErrInvalidInput
	}
	return nil
}
