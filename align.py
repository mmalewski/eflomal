#!/usr/bin/env python3

from eflomal import read_text, write_text, align

import sys, argparse, random, os, io
from tempfile import NamedTemporaryFile

def main():
    parser = argparse.ArgumentParser(
        description='eflomal: efficient low-memory aligner')
    parser.add_argument(
        '-v', '--verbose', dest='verbose',
        action='store_true', help='Enable verbose output')
    parser.add_argument(
        '--debug', dest='debug',
        action='store_true', help='Enable gdb debugging of eflomal binary')
    parser.add_argument(
        '--overwrite', dest='overwrite',
        action='store_true', help='Overwrite existing output files')
    parser.add_argument(
        '--null-prior', dest='null_prior', default=0.2, metavar='X',
        type=float, help='Prior probability of NULL alignment')
    parser.add_argument(
        '-m', '--model', dest='model', default=3, metavar='N',
        type=int, help='Model (1 = IBM1, 2 = IBM1+HMM, 3 = IBM1+HMM+fertility)')
    parser.add_argument(
        '--source-prefix', dest='source_prefix_len', default=0, metavar='N',
        type=int, help='Length of prefix for stemming (source)')
    parser.add_argument(
        '--source-suffix', dest='source_suffix_len', default=0, metavar='N',
        type=int, help='Length of suffix for stemming (source)')
    parser.add_argument(
        '--target-prefix', dest='target_prefix_len', default=0, metavar='N',
        type=int, help='Length of prefix for stemming (target)')
    parser.add_argument(
        '--target-suffix', dest='target_suffix_len', default=0, metavar='N',
        type=int, help='Length of suffix for stemming (target)')
    parser.add_argument(
        '-l', '--length', dest='length', default=1.0, metavar='X',
        type=float, help='Relative number of sampling iterations')
    parser.add_argument(
        '-1', '--ibm1-iters', dest='iters1', default=None, metavar='X',
        type=int, help='Number of IBM1 iterations (overrides --length)')
    parser.add_argument(
        '-2', '--hmm-iters', dest='iters2', default=None, metavar='X',
        type=int, help='Number of HMM iterations (overrides --length)')
    parser.add_argument(
        '-3', '--fert-iters', dest='iters3', default=None, metavar='X',
        type=int,
        help='Number of HMM+fertility iterations (overrides --length)')
    parser.add_argument(
        '--n-samplers', dest='n_samplers', default=3, metavar='X',
        type=int, help='Number of independent samplers to run')
    parser.add_argument(
        '-s', '--source', dest='source_filename', type=str, metavar='filename',
        help='Source text filename')
    parser.add_argument(
        '-t', '--target', dest='target_filename', type=str, metavar='filename',
        help='Target text filename')
    parser.add_argument(
        '-i', '--input', dest='joint_filename', type=str, metavar='filename',
        help='fast_align style ||| separated file')
    parser.add_argument(
        '-f', '--forward-links', dest='links_filename_fwd', type=str,
        metavar='filename',
        help='Filename to write forward direction alignments to')
    parser.add_argument(
        '-r', '--reverse-links', dest='links_filename_rev', type=str,
        metavar='filename',
        help='Filename to write reverse direction alignments to')
    parser.add_argument(
        '-p', '--priors', dest='priors_filename', type=str, metavar='filename',
        help='Filename of lexical priors')
 
    args = parser.parse_args()

    if not (args.joint_filename or (args.source_filename and
        args.target_filename)):
        print('ERROR: need to specify either -s and -t, or -i',
                file=sys.stderr, flush=True)
        sys.exit(1)

    for filename in ((args.joint_filename,) if args.joint_filename else 
                     (args.source_filename, args.target_filename)):
        if not os.path.exists(filename):
            print('ERROR: input file %s does not exist!' % filename,
                  file=sys.stderr, flush=True)
            sys.exit(1)

    for filename in (args.links_filename_fwd, args.links_filename_rev):
        if (not args.overwrite) and (filename is not None) \
                and os.path.exists(filename):
            print('ERROR: output file %s exists, will not overwrite!' % \
                    filename,
                  file=sys.stderr, flush=True)
            sys.exit(1)

    if args.priors_filename:
        if args.verbose:
            print('Reading lexical priors from %s...' %
                    args.priors_filename,
                  file=sys.stderr, flush=True)

        priors_list = []
        with open(args.priors_filename, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                fields = line.rstrip('\n').split('\t')
                if len(fields) != 3:
                    print('ERROR: priors file %s line %d contains %d '
                          'tab-separated fields but should have 3' % (
                              args.priors_filename, i+1, len(fields)),
                          file=sys.stderr, flush=True)
                    sys.exit(1)
                try:
                    alpha = float(fields[2])
                except ValueError:
                    print('ERROR: priors file %s line %d contains alpha '
                          'value of "%s" which is not numeric' % (
                              args.priors_filename, i+1, fields[2]),
                          file=sys.stderr, flush=True)
                    sys.exit(1)
                priors_list.append((fields[0], fields[1], alpha))

    if args.joint_filename:
        if args.verbose:
            print('Reading source/target sentences from %s...' %
                    args.joint_filename,
                  file=sys.stderr, flush=True)
        with open(args.joint_filename, 'r', encoding='utf-8') as f:
            src_sents_text = []
            trg_sents_text = []
            for i, line in enumerate(f):
                fields = line.strip().split(' ||| ')
                if len(fields) != 2:
                    print('ERROR: line %d of %s does not contain a single |||'
                          ' separator, or sentence(s) are empty!' % (
                              i+1, args.joint_filename),
                          file=sys.stderr, flush=True)
                    sys.exit(1)
                src_sents_text.append(fields[0])
                trg_sents_text.append(fields[1])
            src_text = '\n'.join(src_sents_text) + '\n'
            trg_text = '\n'.join(trg_sents_text) + '\n'
            src_sents_text = None
            trg_sents_text = None

        with io.StringIO(src_text) as f:
            src_sents, src_index = read_text(
                    f, True, args.source_prefix_len, args.source_suffix_len)
            n_src_sents = len(src_sents)
            src_voc_size = len(src_index)
            srcf = NamedTemporaryFile('wb')
            write_text(srcf, tuple(src_sents), src_voc_size)
            src_sents = None
            src_text = None

        with io.StringIO(trg_text) as f:
            trg_sents, trg_index = read_text(
                    f, True, args.target_prefix_len, args.target_suffix_len)
            trg_voc_size = len(trg_index)
            n_trg_sents = len(trg_sents)
            trgf = NamedTemporaryFile('wb')
            write_text(trgf, tuple(trg_sents), trg_voc_size)
            trg_sents = None
            trg_text = None

        if args.priors_filename:
            priors_indexed = {}
            for src_word, trg_word, alpha in priors_list:
                if src_word == '<NULL>':
                    e = 0
                else:
                    src_word = src_word.lower()
                    if args.source_prefix_len != 0:
                        src_word = src_word[:args.source_prefix_len]
                    if args.source_suffix_len != 0:
                        src_word = src_word[-args.source_suffix_len:]
                    e = src_index.get(src_word)
                    if e is not None:
                        e = e + 1

                if trg_word == '<NULL>':
                    f = 0
                else:
                    trg_word = trg_word.lower()
                    if args.target_prefix_len != 0:
                        trg_word = trg_word[:args.target_prefix_len]
                    if args.target_suffix_len != 0:
                        trg_word = trg_word[-args.target_suffix_len:]
                    f = trg_index.get(trg_word)
                    if f is not None:
                        f = f + 1

                if (e is not None) and (f is not None):
                    priors_indexed[(e,f)] = priors_indexed.get((e,f), 0.0) \
                            + alpha

            if args.verbose:
                print('%d (of %d) pairs of lexical priors used' % (
                    len(priors_indexed), len(priors_list)),
                        file=sys.stderr)
            priorsf = NamedTemporaryFile('w', encoding='utf-8')
            print('%d %d %d' % (
                len(src_index)+1, len(trg_index)+1, len(priors_indexed)),
                file=priorsf)
            for (e, f), alpha in sorted(priors_indexed.items()):
                print('%d %d %g' % (e, f, alpha), file=priorsf)
            priorsf.flush()

        trg_index = None
        src_index = None

    else:
        if args.verbose:
            print('Reading source text from %s...' % args.source_filename,
                  file=sys.stderr, flush=True)
        with open(args.source_filename, 'r', encoding='utf-8') as f:
            src_sents, src_index = read_text(
                    f, True, args.source_prefix_len, args.source_suffix_len)
            n_src_sents = len(src_sents)
            src_voc_size = len(src_index)
            src_index = None
            srcf = NamedTemporaryFile('wb')
            write_text(srcf, tuple(src_sents), src_voc_size)
            src_sents = None

        if args.verbose:
            print('Reading target text from %s...' % args.target_filename,
                  file=sys.stderr, flush=True)
        with open(args.target_filename, 'r', encoding='utf-8') as f:
            trg_sents, trg_index = read_text(
                    f, True, args.target_prefix_len, args.target_suffix_len)
            trg_voc_size = len(trg_index)
            n_trg_sents = len(trg_sents)
            trg_index = None
            trgf = NamedTemporaryFile('wb')
            write_text(trgf, tuple(trg_sents), trg_voc_size)
            trg_sents = None

        if n_src_sents != n_trg_sents:
            print('ERROR: number of sentences differ in input files (%d vs %d)' % (
                    n_src_sents, n_trg_sents),
                  file=sys.stderr, flush=True)
            sys.exit(1)

    iters = (args.iters1, args.iters2, args.iters3)
    if any(x is None for x in iters[:args.model]):
        iters = None

    if args.verbose:
        print('Aligning %d sentences...' % n_src_sents,
              file=sys.stderr, flush=True)

    align(srcf.name, trgf.name,
          links_filename_fwd=args.links_filename_fwd,
          links_filename_rev=args.links_filename_rev,
          statistics_filename=None,
          scores_filename=None,
          priors_filename=(None if args.priors_filename is None
                           else priorsf.name),
          model=args.model,
          n_iterations=iters,
          n_samplers=args.n_samplers,
          quiet=not args.verbose,
          rel_iterations=args.length,
          null_prior=args.null_prior,
          use_gdb=args.debug)

    srcf.close()
    trgf.close()
    if args.priors_filename:
        priorsf.close()


if __name__ == '__main__': main()

