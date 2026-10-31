package domain

import (
	"sort"
	"strings"
	"unicode"
	"unicode/utf8"
)

// SelectKnowledge is deliberately labelled keyword retrieval. It uses Chinese
// bigrams and word tokens; it is not a vector search and sends no full database.
func SelectKnowledge(records []Knowledge, question, productTitle string) []Knowledge {
	tokens := keywords(question + " " + productTitle)
	type candidate struct {
		k     Knowledge
		score int
	}
	candidates := []candidate{}
	for _, k := range records {
		title, body := strings.ToLower(k.Title), strings.ToLower(k.Content)
		score := 0
		for token := range tokens {
			if strings.Contains(title, token) {
				score += 3
			}
			if strings.Contains(body, token) {
				score++
			}
		}
		if score > 0 {
			candidates = append(candidates, candidate{k, score})
		}
	}
	sort.Slice(candidates, func(i, j int) bool {
		if candidates[i].score != candidates[j].score {
			return candidates[i].score > candidates[j].score
		}
		return candidates[i].k.ID < candidates[j].k.ID
	})
	out := []Knowledge{}
	remaining := 6000
	for _, c := range candidates {
		n := utf8.RuneCountInString(c.k.Title) + utf8.RuneCountInString(c.k.Content)
		// Do not truncate a policy/exception halfway and change its meaning.
		if n > remaining {
			continue
		}
		out = append(out, c.k)
		remaining -= n
		if len(out) >= 6 {
			break
		}
	}
	return out
}

func keywords(s string) map[string]struct{} {
	out := map[string]struct{}{}
	var word []rune
	var previous rune
	flush := func() {
		if len(word) > 1 {
			out[string(word)] = struct{}{}
		}
		word = nil
	}
	for _, r := range strings.ToLower(s) {
		if unicode.Is(unicode.Han, r) {
			flush()
			if previous != 0 {
				out[string([]rune{previous, r})] = struct{}{}
			}
			previous = r
			continue
		}
		previous = 0
		if unicode.IsLetter(r) || unicode.IsDigit(r) {
			word = append(word, r)
		} else {
			flush()
		}
	}
	flush()
	return out
}
