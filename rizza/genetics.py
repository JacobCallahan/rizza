# -*- encoding: utf-8 -*-
"""Genetic algorithm base classes."""
import random
from collections import deque
import attr


@attr.s()
class Population(object):
    """This class is the controller for the population of Orgamisms."""

    gene_base = attr.ib(
        validator=attr.validators.instance_of(list), cmp=False, repr=False)
    population_count = attr.ib(default=20)
    population = attr.ib(default=attr.Factory(list), cmp=False)
    top_scores = attr.ib(default=deque(maxlen=200), repr=False)
    rev_pop_sort = attr.ib(default=False, cmp=False, repr=False)

    def _breed_pair(self, organism1, organism2):
        """Breed two organisms together.

        The first has a greater chance of passing their genes on.
        Random mutation is then given a chance to change the child.

        """
        new_gene_list = []
        gene_list1, gene_list2 = (organism1.genes, organism2.genes)
        for i in range(len(self.gene_base)):
            if random.random() <= 0.75:
                if gene_list1[i] not in new_gene_list:  # avoid duplicates
                    new_gene_list.append(gene_list1[i])
                elif gene_list2[i] not in new_gene_list:
                    new_gene_list.append(gene_list2[i])
            else:
                if gene_list2[i] not in new_gene_list:
                    new_gene_list.append(gene_list2[i])
                elif gene_list1[i] not in new_gene_list:
                    new_gene_list.append(gene_list1[i])

        # Add in any original genes that were removed in the process
        for gene in self.gene_base:
            if gene not in new_gene_list:
                new_gene_list.append(gene)

        org = Organism(genes=new_gene_list)

        # Randomly mutate the organism
        if random.random() <= 0.1:
            org.mutate(self.gene_base)
        # If we have reached a local maximum, force some diversity
        if len(self.top_scores) == 200 and self.top_scores[0] == self.top_scores[-1]:
            if random.random() <= 0.5:
                org.generate_genes()
            else:
                org.mutate(self.gene_base)

        return org

    def gen_population(self):
        """Generate a population of organisms."""
        self.population = []
        for _ in range(self.population_count):
            org = Organism(genes=self.gene_base[:])
            org.generate_genes()
            self.population.append(org)

    def breed_population(self, pool_percentage=50):
        """"Cross breed the population with only the top percentage.

        :param pool_percentage: Percentage defines primary breeder cutoff.

        """
        # Create the breeding order. Those on top get more iterations.
        self.sort_population()
        breeders = self.population[
            :int(self.population_count * (float(pool_percentage) / 100))
        ]
        self.top_scores.append(breeders[0].points)
        i = 0
        while self.population_count > len(breeders):
            breeders.extend(
                [breeders[i]] * 2
            )
            i += 1

        # Create a shuffled duplicate of the populationto breed against
        shuffled = self.population[:]
        random.shuffle(shuffled)
        next_generation = [Organism(genes=breeders[0].genes[:])]  # boldly go!
        for org1, org2 in zip(breeders, shuffled):
            next_generation.append(self._breed_pair(org1, org2))
        self.population = next_generation[:self.population_count - 1]

    def sort_population(self, reverse=None):
        """Sort the population by the number of points they have."""
        reverse = reverse or self.rev_pop_sort
        self.population = sorted(
            self.population, key=lambda org: org.points, reverse=reverse)


@attr.s(slots=True)
class Organism(object):
    """The is the actor class that is the target of evolution."""

    genes = attr.ib(validator=attr.validators.instance_of(list), cmp=False)
    points = attr.ib(default=0)

    def generate_genes(self):
        """Randomly sort the genes to provide different combinations."""
        random.shuffle(self.genes)

    def mutate(self, gene_base=None):
        """Randomly mutate the list by swapping two genes around."""
        if random.random() < 0.1:
            gene1 = random.randint(0, len(self.genes) - 1)
            gene2 = random.randint(0, len(self.genes) - 1)
            self.genes[gene1], self.genes[gene2] = (
                self.genes[gene2], self.genes[gene1])
        else:  # Or we'll mutate to have a new/duplicate value introduced
            genes = gene_base or self.genes
            self.genes[random.randint(0, len(self.genes) - 1)] = random.choice(genes)
