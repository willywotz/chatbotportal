push-tag:
	$(if $(TAG),,$(error Error: TAG is required. Use: make push-tag TAG=v1.0.0))
	git tag $(TAG)
	git push origin $(TAG)

graphify:
  graphify extract . --force --code-only
