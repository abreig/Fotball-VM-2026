# Fotball-VM 2026 - prediksjonspipeline (ren Python, ingen avhengigheter)

PYTHON ?= python3

.PHONY: data fetch predict serve test clean

# Full pipeline: hent ferske data og bygg prediksjoner
data: fetch predict

fetch:
	$(PYTHON) -m pipeline.fetch

predict:
	$(PYTHON) -m pipeline.predict

# Kjør nettsiden lokalt på http://localhost:8000
serve:
	$(PYTHON) -m http.server 8000 --directory site

test:
	$(PYTHON) -m unittest discover -s tests -v

clean:
	rm -rf data/cache/*
