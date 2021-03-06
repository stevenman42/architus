import numpy as np
import operator
import random
import matplotlib
matplotlib.use('agg')

import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
from collections import namedtuple


COLORS = ['b','g','r','c','m','k']

def generate(key, message_counts, word_counts, victim):
    #sorted(range(len(a)), key=lambda i: a[i])[-5:]
    colors = random.sample(COLORS, 2)
    top_5_mesages = sorted(message_counts.items(), key=operator.itemgetter(1))[-5:]

    if victim and victim not in [m[0] for m in top_5_mesages]:
        top_5_mesages[0] = (victim, message_counts[victim] if victim in message_counts else 0)

    n_groups = len(top_5_mesages)


    fig, ax = plt.subplots()

    index = np.arange(n_groups)
    bar_width = 0.35

    opacity = 0.4
    error_config = {'ecolor': '0.3'}

    ax.bar(index, [m[1] for m in reversed(top_5_mesages)], bar_width,
                    alpha=opacity, color=colors[0],
                    label='Messages')

    ax.bar(index + bar_width, [word_counts[m[0]] for m in reversed(top_5_mesages)], bar_width,
                    alpha=opacity, color=colors[1],
                    label='Words')

    ax.set_xlabel('User')
    ax.set_ylabel('Count')
    #ax.set_title('Scores by group and gender')
    ax.set_xticks(index + bar_width / 2)
    ax.set_xticklabels([m[0].display_name for m in reversed(top_5_mesages)])
    ax.legend()

    fig.tight_layout()

    plt.savefig('res/word%s.png' % key, bbox_inches='tight', edgecolor=None)
    plt.close()
