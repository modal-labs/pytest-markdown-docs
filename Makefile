build:
	uv build

clean:
	rm -rf dist

publish: clean build
	uv publish
