# Basic Python example

From the repository root, start the API in one terminal:

```bash
make api
```

Then, in another terminal:

```bash
export DMA_API_KEY=dma-local-development-key
make example
```

The example stores a semantic memory and retrieves it through the same
`dma-sdk` interface an agent application uses.
