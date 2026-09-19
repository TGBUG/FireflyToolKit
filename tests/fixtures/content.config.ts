// A synthetic fixture shaped like the theme's real src/content.config.ts.
//
// It deliberately includes the awkwards bits that a naive scanner gets wrong:
// the multi-line `z` `.array(` split, comments containing commas and braces, and
// an empty schema. The theme itself is not vendored here.

import { defineCollection } from "astro:content";
import { glob } from "astro/loaders";
import { z } from "astro/zod";

type PostData = {
	title: string;
	published: Date;
};

const postsCollection = defineCollection({
	loader: glob({ pattern: "**/*.{md,mdx}", base: "./src/content/posts" }),
	schema: z.object({
		title: z.string(),
		published: z.date(),
		author: z.string(),
		updated: z.date().optional(),
		// A comment with a comma, and a z.object({}) in it, both of which would
		// derail a scanner that splits on the first comma it sees.
		tags: z.array(z.string()).optional().default([]),
		seriesOrder: z.number().optional(),

		/* The method name sits on the next line, the shape that hid a bug. */
		link: z
			.array(
				z.object({
					label: z.string(),
					value: z.string(),
				}),
			)
			.optional()
			.default([]),
	}),
});

const specCollection = defineCollection({
	loader: glob({ pattern: "**/*.{md,mdx}", base: "./src/content/spec" }),
	schema: z.object({}),
});

export const collections: {
	posts: typeof postsCollection;
	spec: typeof specCollection;
} = {
	posts: postsCollection,
	spec: specCollection,
};
