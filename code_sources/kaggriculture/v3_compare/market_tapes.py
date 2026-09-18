"""The two market tapes, expanded. Extracted from submission/v3_base.py.

These were the blobs at lines 414 and 645 -- 1.5 KB and 1.8 KB of base85 that
nothing could read. Each row is one step's market order list.

_V17_R5_MARKETS  720 rows  read by _v17_r5_counter, gated on _V17_R5_ITEMS
                           ('MELON','MILK','STRAWBERRY','WOOL') at fraction 0.5
_V17_MD_MARKETS  719 rows  read by _v17_md_counter, fraction 2.0

Both guards DO fire in pool play -- 16 and 140 action-changing turns over 20
episodes -- so they are live, not vestigial. This file is for reading; the
agent reads its own copies.
"""

_V17_R5_MARKETS = [
    [["BUY_PRODUCT", "WHEAT", 14], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["BUY_ANIMAL", "COW", 1], ["BUY_ANIMAL", "SHEEP", 4], ["BUY_SEED", "MELON", 5], ["BUY_SEED", "WHEAT", 5], ["HIRE"]],  #   0
    [["SELL", "WHEAT", 9], ["BUY_SEED", "MELON", 3], ["BUY_SEED", "WHEAT", 2]],  #   1
    [],  #   2
    [],  #   3
    [],  #   4
    [],  #   5
    [],  #   6
    [],  #   7
    [],  #   8
    [],  #   9
    [],  #  10
    [],  #  11
    [],  #  12
    [],  #  13
    [],  #  14
    [],  #  15
    [],  #  16
    [],  #  17
    [],  #  18
    [],  #  19
    [],  #  20
    [],  #  21
    [],  #  22
    [],  #  23
    [["HIRE"]],  #  24
    [],  #  25
    [],  #  26
    [],  #  27
    [],  #  28
    [],  #  29
    [],  #  30
    [],  #  31
    [],  #  32
    [],  #  33
    [],  #  34
    [],  #  35
    [],  #  36
    [],  #  37
    [],  #  38
    [],  #  39
    [],  #  40
    [],  #  41
    [],  #  42
    [],  #  43
    [],  #  44
    [],  #  45
    [],  #  46
    [],  #  47
    [["SELL", "FERTILIZER", 5], ["HIRE"], ["HIRE"], ["BUY_PRODUCT", "WHEAT", 7]],  #  48
    [],  #  49
    [],  #  50
    [["BUY_PRODUCT", "WHEAT", 1], ["BUY_PRODUCT", "WHEAT", 1]],  #  51
    [],  #  52
    [["BUY_PRODUCT", "WHEAT", 6]],  #  53
    [],  #  54
    [],  #  55
    [],  #  56
    [],  #  57
    [],  #  58
    [],  #  59
    [],  #  60
    [],  #  61
    [["BUY_PRODUCT", "WHEAT", 1]],  #  62
    [],  #  63
    [],  #  64
    [["BUY_PRODUCT", "WHEAT", 1]],  #  65
    [],  #  66
    [],  #  67
    [],  #  68
    [],  #  69
    [],  #  70
    [],  #  71
    [["SELL", "FERTILIZER", 5], ["HIRE"], ["HIRE"], ["BUY_SEED", "WHEAT", 1], ["BUY_SEED", "STRAWBERRY", 3]],  #  72
    [],  #  73
    [["HIRE"]],  #  74
    [["BUY_PRODUCT", "WHEAT", 1]],  #  75
    [],  #  76
    [],  #  77
    [],  #  78
    [],  #  79
    [],  #  80
    [["BUY_PRODUCT", "WHEAT", 1]],  #  81
    [["BUY_PRODUCT", "WHEAT", 1]],  #  82
    [],  #  83
    [],  #  84
    [],  #  85
    [["BUY_PRODUCT", "WHEAT", 1]],  #  86
    [],  #  87
    [["BUY_PRODUCT", "WHEAT", 1]],  #  88
    [],  #  89
    [],  #  90
    [],  #  91
    [],  #  92
    [],  #  93
    [],  #  94
    [],  #  95
    [["SELL", "FERTILIZER", 5], ["HIRE"], ["HIRE"], ["HIRE"]],  #  96
    [["BUY_SEED", "WHEAT", 5], ["HIRE"]],  #  97
    [],  #  98
    [],  #  99
    [["BUY_SEED", "WHEAT", 1]],  # 100
    [["BUY_PRODUCT", "WHEAT", 1]],  # 101
    [],  # 102
    [],  # 103
    [],  # 104
    [],  # 105
    [],  # 106
    [],  # 107
    [],  # 108
    [],  # 109
    [],  # 110
    [],  # 111
    [],  # 112
    [],  # 113
    [],  # 114
    [],  # 115
    [],  # 116
    [],  # 117
    [["BUY_PRODUCT", "WHEAT", 1]],  # 118
    [],  # 119
    [["SELL", "FERTILIZER", 5], ["HIRE"], ["HIRE"], ["BUY_SEED", "STRAWBERRY", 4], ["BUY_ANIMAL", "COW", 1], ["HIRE"]],  # 120
    [["BUY_PRODUCT", "WHEAT", 1]],  # 121
    [],  # 122
    [],  # 123
    [["BUY_PRODUCT", "WHEAT", 1]],  # 124
    [],  # 125
    [],  # 126
    [],  # 127
    [],  # 128
    [],  # 129
    [],  # 130
    [],  # 131
    [],  # 132
    [],  # 133
    [],  # 134
    [],  # 135
    [],  # 136
    [],  # 137
    [["BUY_PRODUCT", "WHEAT", 1]],  # 138
    [],  # 139
    [],  # 140
    [["BUY_PRODUCT", "WHEAT", 2]],  # 141
    [["BUY_PRODUCT", "WHEAT", 1]],  # 142
    [],  # 143
    [["SELL", "FERTILIZER", 5], ["HIRE"], ["HIRE"], ["HIRE"]],  # 144
    [],  # 145
    [],  # 146
    [["BUY_PRODUCT", "WHEAT", 1]],  # 147
    [["BUY_SEED", "WHEAT", 1], ["BUY_PRODUCT", "WHEAT", 1]],  # 148
    [["BUY_PRODUCT", "WHEAT", 1]],  # 149
    [["SELL", "WHEAT", 17]],  # 150
    [],  # 151
    [],  # 152
    [],  # 153
    [],  # 154
    [],  # 155
    [["BUY_SEED", "STRAWBERRY", 3]],  # 156
    [],  # 157
    [],  # 158
    [],  # 159
    [["SELL", "WOOL", 9], ["SELL", "FERTILIZER", 3], ["BUY_LAND"]],  # 160
    [["BUY_ANIMAL", "COW", 2], ["HIRE"]],  # 161
    [],  # 162
    [],  # 163
    [],  # 164
    [],  # 165
    [],  # 166
    [],  # 167
    [["SELL", "WOOL", 17], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["BUY_ANIMAL", "COW", 2], ["BUY_PRODUCT", "WHEAT", 2]],  # 168
    [["BUY_PRODUCT", "WHEAT", 4], ["BUY_SEED", "STRAWBERRY", 9], ["BUY_SEED", "WHEAT", 3], ["BUY_PRODUCT", "WHEAT", 2]],  # 169
    [],  # 170
    [["BUY_PRODUCT", "WHEAT", 1]],  # 171
    [],  # 172
    [["BUY_PRODUCT", "WHEAT", 3], ["BUY_PRODUCT", "WHEAT", 1]],  # 173
    [],  # 174
    [["SELL", "FERTILIZER", 3]],  # 175
    [],  # 176
    [],  # 177
    [["BUY_PRODUCT", "WHEAT", 1]],  # 178
    [],  # 179
    [],  # 180
    [],  # 181
    [["BUY_PRODUCT", "WHEAT", 1]],  # 182
    [],  # 183
    [],  # 184
    [],  # 185
    [],  # 186
    [],  # 187
    [],  # 188
    [],  # 189
    [],  # 190
    [],  # 191
    [["SELL", "FERTILIZER", 7], ["HIRE"], ["BUY_SEED", "WHEAT", 3], ["HIRE"], ["HIRE"], ["HIRE"], ["BUY_ANIMAL", "COW", 2], ["HIRE"], ["HIRE"]],  # 192
    [["BUY_PRODUCT", "WHEAT", 1], ["BUY_SEED", "STRAWBERRY", 2]],  # 193
    [],  # 194
    [["SELL", "WHEAT", 2]],  # 195
    [],  # 196
    [["BUY_PRODUCT", "WHEAT", 5]],  # 197
    [["BUY_SEED", "WHEAT", 1]],  # 198
    [],  # 199
    [],  # 200
    [],  # 201
    [],  # 202
    [],  # 203
    [],  # 204
    [],  # 205
    [],  # 206
    [],  # 207
    [],  # 208
    [["BUY_SEED", "WHEAT", 5]],  # 209
    [],  # 210
    [["SELL", "WHEAT", 6]],  # 211
    [],  # 212
    [],  # 213
    [],  # 214
    [["SELL", "FERTILIZER", 3]],  # 215
    [["SELL", "FERTILIZER", 10], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 216
    [],  # 217
    [],  # 218
    [],  # 219
    [],  # 220
    [],  # 221
    [["SELL", "WHEAT", 7]],  # 222
    [],  # 223
    [["BUY_PRODUCT", "WHEAT", 1]],  # 224
    [],  # 225
    [],  # 226
    [],  # 227
    [],  # 228
    [["BUY_PRODUCT", "WHEAT", 1]],  # 229
    [],  # 230
    [],  # 231
    [],  # 232
    [["SELL", "MILK", 3]],  # 233
    [],  # 234
    [["BUY_PRODUCT", "WHEAT", 1]],  # 235
    [],  # 236
    [],  # 237
    [],  # 238
    [],  # 239
    [["SELL", "WOOL", 18], ["BUY_LAND"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 240
    [["HIRE"], ["SELL", "FERTILIZER", 16], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["BUY_SEED", "MELON", 7], ["HIRE"]],  # 241
    [],  # 242
    [],  # 243
    [],  # 244
    [],  # 245
    [],  # 246
    [],  # 247
    [["BUY_PRODUCT", "WHEAT", 4]],  # 248
    [],  # 249
    [],  # 250
    [],  # 251
    [["SELL", "MELON", 10], ["BUY_SEED", "STRAWBERRY", 8], ["BUY_PRODUCT", "WHEAT", 1], ["BUY_SEED", "MELON", 5]],  # 252
    [["BUY_SEED", "STRAWBERRY", 2]],  # 253
    [],  # 254
    [["SELL", "MELON", 6], ["BUY_PRODUCT", "WHEAT", 15], ["BUY_SEED", "STRAWBERRY", 6]],  # 255
    [],  # 256
    [["SELL", "MELON", 11]],  # 257
    [],  # 258
    [],  # 259
    [["SELL", "MELON", 6]],  # 260
    [],  # 261
    [["SELL", "MELON", 6], ["BUY_SEED", "WHEAT", 1]],  # 262
    [],  # 263
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 264
    [["HIRE"]],  # 265
    [["BUY_SEED", "WHEAT", 4]],  # 266
    [],  # 267
    [],  # 268
    [],  # 269
    [],  # 270
    [["BUY_PRODUCT", "WHEAT", 1]],  # 271
    [],  # 272
    [],  # 273
    [],  # 274
    [],  # 275
    [["SELL", "FERTILIZER", 12]],  # 276
    [],  # 277
    [["SELL", "WHEAT", 11]],  # 278
    [],  # 279
    [],  # 280
    [],  # 281
    [],  # 282
    [],  # 283
    [],  # 284
    [],  # 285
    [],  # 286
    [],  # 287
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 288
    [["HIRE"], ["HIRE"]],  # 289
    [["BUY_SEED", "WHEAT", 8], ["BUY_PRODUCT", "WHEAT", 1]],  # 290
    [],  # 291
    [],  # 292
    [],  # 293
    [],  # 294
    [],  # 295
    [],  # 296
    [],  # 297
    [],  # 298
    [["SELL", "FERTILIZER", 10]],  # 299
    [],  # 300
    [],  # 301
    [["SELL", "MILK", 6]],  # 302
    [["SELL", "WHEAT", 2]],  # 303
    [],  # 304
    [],  # 305
    [],  # 306
    [],  # 307
    [["SELL", "WHEAT", 12]],  # 308
    [["SELL", "WHEAT", 1]],  # 309
    [],  # 310
    [],  # 311
    [["SELL", "WHEAT", 24], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 312
    [["HIRE"]],  # 313
    [["BUY_PRODUCT", "WHEAT", 2], ["BUY_SEED", "WHEAT", 1]],  # 314
    [],  # 315
    [["SELL", "FERTILIZER", 16]],  # 316
    [["BUY_PRODUCT", "WHEAT", 2]],  # 317
    [],  # 318
    [["BUY_PRODUCT", "WHEAT", 2]],  # 319
    [["BUY_PRODUCT", "WHEAT", 2], ["BUY_PRODUCT", "WHEAT", 1]],  # 320
    [["BUY_PRODUCT", "WHEAT", 2]],  # 321
    [],  # 322
    [],  # 323
    [],  # 324
    [],  # 325
    [],  # 326
    [],  # 327
    [],  # 328
    [["BUY_PRODUCT", "WHEAT", 3]],  # 329
    [["SELL", "MILK", 3]],  # 330
    [["BUY_PRODUCT", "WHEAT", 3], ["BUY_PRODUCT", "WHEAT", 1]],  # 331
    [],  # 332
    [],  # 333
    [],  # 334
    [["SELL", "MILK", 4]],  # 335
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 336
    [["HIRE"], ["HIRE"], ["HIRE"]],  # 337
    [],  # 338
    [["BUY_PRODUCT", "WHEAT", 3]],  # 339
    [["BUY_PRODUCT", "WHEAT", 1]],  # 340
    [["SELL", "FERTILIZER", 9]],  # 341
    [["BUY_PRODUCT", "WHEAT", 1]],  # 342
    [],  # 343
    [],  # 344
    [],  # 345
    [["BUY_PRODUCT", "WHEAT", 1]],  # 346
    [],  # 347
    [],  # 348
    [],  # 349
    [],  # 350
    [],  # 351
    [["BUY_PRODUCT", "WHEAT", 1]],  # 352
    [],  # 353
    [],  # 354
    [["BUY_PRODUCT", "WHEAT", 3]],  # 355
    [],  # 356
    [],  # 357
    [["SELL", "MILK", 13]],  # 358
    [["BUY_PRODUCT", "WHEAT", 4]],  # 359
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 360
    [["BUY_PRODUCT", "WHEAT", 1], ["SELL", "WOOL", 8], ["HIRE"], ["SELL", "MILK", 3]],  # 361
    [["SELL", "MILK", 6], ["BUY_SEED", "WHEAT", 4]],  # 362
    [],  # 363
    [],  # 364
    [["BUY_PRODUCT", "WHEAT", 5], ["SELL", "FERTILIZER", 4]],  # 365
    [],  # 366
    [["BUY_PRODUCT", "WHEAT", 1]],  # 367
    [],  # 368
    [],  # 369
    [],  # 370
    [],  # 371
    [],  # 372
    [],  # 373
    [],  # 374
    [],  # 375
    [["BUY_PRODUCT", "WHEAT", 1]],  # 376
    [["SELL", "MILK", 12]],  # 377
    [],  # 378
    [],  # 379
    [["SELL", "WOOL", 8]],  # 380
    [],  # 381
    [],  # 382
    [["BUY_PRODUCT", "WHEAT", 1]],  # 383
    [["HIRE"], ["SELL", "FERTILIZER", 2], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 384
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["BUY_SEED", "WHEAT", 3], ["BUY_PRODUCT", "WHEAT", 1]],  # 385
    [["SELL", "STRAWBERRY", 2], ["BUY_SEED", "WHEAT", 5]],  # 386
    [["BUY_PRODUCT", "WHEAT", 1]],  # 387
    [],  # 388
    [["SELL", "MILK", 3]],  # 389
    [],  # 390
    [],  # 391
    [],  # 392
    [],  # 393
    [],  # 394
    [["BUY_PRODUCT", "WHEAT", 2]],  # 395
    [],  # 396
    [],  # 397
    [],  # 398
    [],  # 399
    [["SELL", "STRAWBERRY", 8]],  # 400
    [["BUY_SEED", "WHEAT", 1]],  # 401
    [],  # 402
    [["BUY_SEED", "WHEAT", 1]],  # 403
    [],  # 404
    [["SELL", "STRAWBERRY", 14], ["SELL", "WHEAT", 5]],  # 405
    [["SELL", "MILK", 24], ["BUY_SEED", "WHEAT", 1]],  # 406
    [],  # 407
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 408
    [["HIRE"], ["HIRE"], ["BUY_PRODUCT", "WHEAT", 1], ["HIRE"]],  # 409
    [],  # 410
    [["SELL", "FERTILIZER", 7]],  # 411
    [],  # 412
    [],  # 413
    [["SELL", "WHEAT", 3], ["BUY_PRODUCT", "WHEAT", 1]],  # 414
    [],  # 415
    [["BUY_PRODUCT", "WHEAT", 2]],  # 416
    [["BUY_PRODUCT", "WHEAT", 1], ["BUY_PRODUCT", "WHEAT", 1]],  # 417
    [],  # 418
    [["SELL", "WOOL", 12]],  # 419
    [],  # 420
    [["BUY_PRODUCT", "WHEAT", 2]],  # 421
    [["SELL", "FERTILIZER", 14]],  # 422
    [["SELL", "STRAWBERRY", 2]],  # 423
    [],  # 424
    [],  # 425
    [],  # 426
    [["SELL", "WOOL", 13]],  # 427
    [],  # 428
    [],  # 429
    [["SELL", "MILK", 3]],  # 430
    [["SELL", "MILK", 7]],  # 431
    [["SELL", "STRAWBERRY", 28], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 432
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 433
    [],  # 434
    [],  # 435
    [["BUY_PRODUCT", "WHEAT", 2]],  # 436
    [["BUY_PRODUCT", "WHEAT", 2]],  # 437
    [["BUY_PRODUCT", "WHEAT", 1]],  # 438
    [],  # 439
    [],  # 440
    [["BUY_PRODUCT", "WHEAT", 2]],  # 441
    [["BUY_PRODUCT", "WHEAT", 2]],  # 442
    [["BUY_PRODUCT", "WHEAT", 4]],  # 443
    [["BUY_PRODUCT", "WHEAT", 1]],  # 444
    [],  # 445
    [["BUY_PRODUCT", "WHEAT", 1]],  # 446
    [],  # 447
    [["BUY_PRODUCT", "WHEAT", 1]],  # 448
    [["SELL", "WHEAT", 4]],  # 449
    [],  # 450
    [["SELL", "MILK", 8]],  # 451
    [["BUY_PRODUCT", "WHEAT", 1], ["BUY_PRODUCT", "WHEAT", 1], ["BUY_SEED", "WHEAT", 1]],  # 452
    [["SELL", "WOOL", 12]],  # 453
    [],  # 454
    [["SELL", "MILK", 9]],  # 455
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 456
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 457
    [["BUY_SEED", "WHEAT", 4]],  # 458
    [],  # 459
    [],  # 460
    [],  # 461
    [["BUY_PRODUCT", "WHEAT", 1]],  # 462
    [],  # 463
    [],  # 464
    [],  # 465
    [],  # 466
    [["SELL", "WHEAT", 19]],  # 467
    [["BUY_PRODUCT", "WHEAT", 1]],  # 468
    [["SELL", "FERTILIZER", 3], ["SELL", "FERTILIZER", 2]],  # 469
    [["SELL", "MILK", 3]],  # 470
    [["BUY_PRODUCT", "WHEAT", 2]],  # 471
    [["SELL", "STRAWBERRY", 12]],  # 472
    [],  # 473
    [],  # 474
    [["BUY_PRODUCT", "WHEAT", 2]],  # 475
    [],  # 476
    [],  # 477
    [],  # 478
    [["SELL", "STRAWBERRY", 16]],  # 479
    [["SELL", "STRAWBERRY", 20], ["SELL", "MILK", 6], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["SELL", "WHEAT", 3], ["HIRE"], ["HIRE"]],  # 480
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["BUY_SEED", "WHEAT", 46]],  # 481
    [],  # 482
    [],  # 483
    [["SELL", "MILK", 7]],  # 484
    [],  # 485
    [["SELL", "MELON", 6]],  # 486
    [],  # 487
    [["SELL", "MELON", 6]],  # 488
    [["BUY_PRODUCT", "WHEAT", 1]],  # 489
    [["SELL", "MELON", 12]],  # 490
    [["SELL", "WHEAT", 1]],  # 491
    [["SELL", "MELON", 6]],  # 492
    [["SELL", "MELON", 10]],  # 493
    [],  # 494
    [["SELL", "MELON", 6]],  # 495
    [["SELL", "MELON", 6]],  # 496
    [],  # 497
    [["BUY_SEED", "WHEAT", 1]],  # 498
    [],  # 499
    [],  # 500
    [],  # 501
    [["SELL", "MILK", 9], ["SELL", "MELON", 15]],  # 502
    [["SELL", "MELON", 6], ["SELL", "WHEAT", 5], ["BUY_SEED", "WHEAT", 2]],  # 503
    [["SELL", "STRAWBERRY", 18], ["SELL", "MELON", 14], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 504
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["BUY_PRODUCT", "WHEAT", 2]],  # 505
    [["SELL", "FERTILIZER", 3]],  # 506
    [["BUY_PRODUCT", "WHEAT", 1]],  # 507
    [],  # 508
    [["BUY_SEED", "WHEAT", 3]],  # 509
    [],  # 510
    [],  # 511
    [],  # 512
    [["SELL", "MILK", 3]],  # 513
    [["BUY_SEED", "WHEAT", 3]],  # 514
    [],  # 515
    [],  # 516
    [],  # 517
    [],  # 518
    [["BUY_SEED", "WHEAT", 3], ["SELL", "MILK", 3]],  # 519
    [["BUY_PRODUCT", "WHEAT", 1]],  # 520
    [],  # 521
    [["SELL", "STRAWBERRY", 10], ["SELL", "WHEAT", 7]],  # 522
    [["BUY_PRODUCT", "WHEAT", 1], ["SELL", "MILK", 14]],  # 523
    [["BUY_PRODUCT", "WHEAT", 1]],  # 524
    [],  # 525
    [],  # 526
    [["SELL", "FERTILIZER", 14], ["SELL", "STRAWBERRY", 4]],  # 527
    [["SELL", "STRAWBERRY", 30], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 528
    [["HIRE"], ["HIRE"], ["HIRE"], ["BUY_PRODUCT", "WHEAT", 1]],  # 529
    [],  # 530
    [],  # 531
    [["BUY_PRODUCT", "WHEAT", 1]],  # 532
    [],  # 533
    [["SELL", "FERTILIZER", 8]],  # 534
    [["BUY_PRODUCT", "WHEAT", 1], ["SELL", "WHEAT", 1]],  # 535
    [],  # 536
    [],  # 537
    [["BUY_PRODUCT", "WHEAT", 2]],  # 538
    [],  # 539
    [],  # 540
    [],  # 541
    [],  # 542
    [["SELL", "WHEAT", 12]],  # 543
    [],  # 544
    [],  # 545
    [],  # 546
    [],  # 547
    [],  # 548
    [],  # 549
    [],  # 550
    [["SELL", "MILK", 13]],  # 551
    [["SELL", "STRAWBERRY", 24], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 552
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["SELL", "MILK", 8]],  # 553
    [],  # 554
    [["SELL", "MILK", 9]],  # 555
    [],  # 556
    [],  # 557
    [["SELL", "FERTILIZER", 5]],  # 558
    [["BUY_SEED", "WHEAT", 1], ["SELL", "MILK", 3]],  # 559
    [["BUY_PRODUCT", "WHEAT", 1]],  # 560
    [["BUY_SEED", "WHEAT", 2]],  # 561
    [],  # 562
    [["BUY_SEED", "WHEAT", 1]],  # 563
    [],  # 564
    [],  # 565
    [["BUY_SEED", "WHEAT", 1]],  # 566
    [],  # 567
    [["SELL", "WOOL", 8]],  # 568
    [["BUY_SEED", "WHEAT", 1]],  # 569
    [],  # 570
    [["SELL", "FERTILIZER", 1], ["BUY_SEED", "WHEAT", 1]],  # 571
    [],  # 572
    [],  # 573
    [],  # 574
    [["SELL", "STRAWBERRY", 13]],  # 575
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 576
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 577
    [],  # 578
    [],  # 579
    [],  # 580
    [],  # 581
    [],  # 582
    [["SELL", "WOOL", 8]],  # 583
    [["SELL", "FERTILIZER", 3]],  # 584
    [],  # 585
    [["BUY_SEED", "WHEAT", 2]],  # 586
    [["SELL", "MILK", 10]],  # 587
    [["SELL", "FERTILIZER", 5]],  # 588
    [],  # 589
    [],  # 590
    [["BUY_SEED", "WHEAT", 3]],  # 591
    [],  # 592
    [["SELL", "MILK", 4], ["SELL", "FERTILIZER", 4]],  # 593
    [["SELL", "STRAWBERRY", 20]],  # 594
    [],  # 595
    [["SELL", "WHEAT", 20]],  # 596
    [["SELL", "WHEAT", 9]],  # 597
    [["SELL", "FERTILIZER", 10]],  # 598
    [["SELL", "MILK", 12]],  # 599
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["SELL", "FERTILIZER", 1]],  # 600
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["BUY_SEED", "WHEAT", 1]],  # 601
    [],  # 602
    [],  # 603
    [],  # 604
    [["BUY_SEED", "WHEAT", 1]],  # 605
    [],  # 606
    [],  # 607
    [["SELL", "FERTILIZER", 5], ["SELL", "WHEAT", 3], ["BUY_SEED", "WHEAT", 2]],  # 608
    [["SELL", "STRAWBERRY", 17], ["SELL", "WHEAT", 31], ["BUY_SEED", "WHEAT", 1]],  # 609
    [],  # 610
    [],  # 611
    [["BUY_SEED", "WHEAT", 1]],  # 612
    [["BUY_SEED", "WHEAT", 1]],  # 613
    [],  # 614
    [["SELL", "STRAWBERRY", 13]],  # 615
    [],  # 616
    [["SELL", "FERTILIZER", 6]],  # 617
    [["BUY_SEED", "WHEAT", 1], ["SELL", "MILK", 8]],  # 618
    [],  # 619
    [["SELL", "FERTILIZER", 2], ["BUY_SEED", "WHEAT", 1], ["BUY_PRODUCT", "WHEAT", 2]],  # 620
    [["SELL", "MILK", 4]],  # 621
    [["SELL", "FERTILIZER", 1]],  # 622
    [],  # 623
    [["SELL", "WHEAT", 30], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 624
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 625
    [["SELL", "FERTILIZER", 9]],  # 626
    [["SELL", "FERTILIZER", 4]],  # 627
    [["BUY_PRODUCT", "WHEAT", 1]],  # 628
    [["BUY_PRODUCT", "WHEAT", 3]],  # 629
    [],  # 630
    [],  # 631
    [["SELL", "WHEAT", 7]],  # 632
    [["BUY_SEED", "WHEAT", 2], ["SELL", "FERTILIZER", 2]],  # 633
    [["SELL", "WOOL", 6]],  # 634
    [],  # 635
    [],  # 636
    [],  # 637
    [["SELL", "MILK", 10]],  # 638
    [],  # 639
    [],  # 640
    [["BUY_SEED", "WHEAT", 1], ["BUY_SEED", "WHEAT", 1]],  # 641
    [],  # 642
    [],  # 643
    [],  # 644
    [["SELL", "STRAWBERRY", 16]],  # 645
    [["SELL", "FERTILIZER", 4]],  # 646
    [],  # 647
    [["SELL", "MILK", 7], ["SELL", "FERTILIZER", 5], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 648
    [["HIRE"], ["HIRE"], ["SELL", "FERTILIZER", 7], ["HIRE"], ["HIRE"], ["HIRE"]],  # 649
    [],  # 650
    [["SELL", "STRAWBERRY", 11]],  # 651
    [],  # 652
    [],  # 653
    [],  # 654
    [],  # 655
    [],  # 656
    [],  # 657
    [],  # 658
    [],  # 659
    [],  # 660
    [["SELL", "WOOL", 10]],  # 661
    [["SELL", "FERTILIZER", 6]],  # 662
    [],  # 663
    [],  # 664
    [["SELL", "MILK", 12]],  # 665
    [["SELL", "MILK", 9], ["SELL", "FERTILIZER", 2]],  # 666
    [],  # 667
    [["SELL", "WHEAT", 10]],  # 668
    [["SELL", "FERTILIZER", 3], ["SELL", "WOOL", 17]],  # 669
    [],  # 670
    [["SELL", "WHEAT", 2]],  # 671
    [["SELL", "WHEAT", 46], ["SELL", "FERTILIZER", 5], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 672
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 673
    [],  # 674
    [],  # 675
    [],  # 676
    [["SELL", "FERTILIZER", 2]],  # 677
    [],  # 678
    [],  # 679
    [],  # 680
    [],  # 681
    [["SELL", "WOOL", 8], ["SELL", "FERTILIZER", 1]],  # 682
    [],  # 683
    [],  # 684
    [],  # 685
    [],  # 686
    [["SELL", "FERTILIZER", 5]],  # 687
    [],  # 688
    [["SELL", "WHEAT", 3]],  # 689
    [["SELL", "MILK", 8], ["SELL", "FERTILIZER", 8]],  # 690
    [["SELL", "FERTILIZER", 4]],  # 691
    [],  # 692
    [["SELL", "FERTILIZER", 1]],  # 693
    [["SELL", "WHEAT", 6]],  # 694
    [],  # 695
    [["SELL", "WHEAT", 53], ["SELL", "FERTILIZER", 5], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 696
    [["HIRE"], ["HIRE"]],  # 697
    [],  # 698
    [],  # 699
    [],  # 700
    [["SELL", "STRAWBERRY", 22], ["SELL", "FERTILIZER", 5]],  # 701
    [["SELL", "MILK", 18]],  # 702
    [["SELL", "MILK", 18]],  # 703
    [],  # 704
    [],  # 705
    [],  # 706
    [],  # 707
    [],  # 708
    [],  # 709
    [],  # 710
    [],  # 711
    [],  # 712
    [["SELL", "WHEAT", 16]],  # 713
    [["SELL", "FERTILIZER", 3]],  # 714
    [["SELL", "MILK", 18], ["SELL", "WHEAT", 26]],  # 715
    [["SELL", "WHEAT", 22], ["SELL", "WHEAT", 1]],  # 716
    [["SELL", "WHEAT", 36]],  # 717
    [["SELL", "FERTILIZER", 5], ["SELL", "WHEAT", 7]],  # 718
    [],  # 719
]

_V17_MD_MARKETS = [
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["BUY_ANIMAL", "COW", 2], ["BUY_ANIMAL", "SHEEP", 2], ["BUY_SEED", "WHEAT", 7], ["BUY_SEED", "MELON", 12], ["BUY_PRODUCT", "WHEAT", 6]],  #   0
    [["SELL", "WHEAT", 3]],  #   1
    [],  #   2
    [],  #   3
    [],  #   4
    [],  #   5
    [["BUY_PRODUCT", "WHEAT", 2]],  #   6
    [],  #   7
    [],  #   8
    [],  #   9
    [],  #  10
    [],  #  11
    [["BUY_PRODUCT", "WHEAT", 1]],  #  12
    [],  #  13
    [],  #  14
    [],  #  15
    [],  #  16
    [],  #  17
    [],  #  18
    [],  #  19
    [],  #  20
    [],  #  21
    [],  #  22
    [],  #  23
    [],  #  24
    [],  #  25
    [],  #  26
    [],  #  27
    [],  #  28
    [],  #  29
    [],  #  30
    [],  #  31
    [],  #  32
    [],  #  33
    [],  #  34
    [],  #  35
    [],  #  36
    [],  #  37
    [],  #  38
    [],  #  39
    [],  #  40
    [],  #  41
    [["SELL", "FERTILIZER", 3], ["BUY_PRODUCT", "WHEAT", 5]],  #  42
    [],  #  43
    [],  #  44
    [],  #  45
    [],  #  46
    [],  #  47
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  #  48
    [],  #  49
    [["BUY_PRODUCT", "WHEAT", 2]],  #  50
    [],  #  51
    [],  #  52
    [],  #  53
    [],  #  54
    [],  #  55
    [["BUY_PRODUCT", "WHEAT", 2]],  #  56
    [],  #  57
    [],  #  58
    [],  #  59
    [],  #  60
    [],  #  61
    [],  #  62
    [],  #  63
    [],  #  64
    [],  #  65
    [],  #  66
    [],  #  67
    [],  #  68
    [],  #  69
    [],  #  70
    [],  #  71
    [["SELL", "FERTILIZER", 4], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  #  72
    [["BUY_ANIMAL", "COW", 1], ["BUY_SEED", "CARROT", 1]],  #  73
    [],  #  74
    [],  #  75
    [],  #  76
    [],  #  77
    [],  #  78
    [],  #  79
    [],  #  80
    [],  #  81
    [],  #  82
    [],  #  83
    [],  #  84
    [],  #  85
    [],  #  86
    [],  #  87
    [],  #  88
    [],  #  89
    [],  #  90
    [],  #  91
    [],  #  92
    [],  #  93
    [],  #  94
    [],  #  95
    [["SELL", "FERTILIZER", 4], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["BUY_PRODUCT", "WHEAT", 6], ["BUY_SEED", "WHEAT", 5]],  #  96
    [["BUY_SEED", "WHEAT", 2]],  #  97
    [],  #  98
    [],  #  99
    [],  # 100
    [],  # 101
    [],  # 102
    [],  # 103
    [],  # 104
    [],  # 105
    [],  # 106
    [],  # 107
    [],  # 108
    [],  # 109
    [],  # 110
    [],  # 111
    [],  # 112
    [],  # 113
    [],  # 114
    [],  # 115
    [],  # 116
    [],  # 117
    [],  # 118
    [],  # 119
    [["SELL", "FERTILIZER", 5], ["SELL", "WHEAT", 8], ["BUY_ANIMAL", "COW", 1], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["BUY_SEED", "STRAWBERRY", 2]],  # 120
    [["SELL", "WHEAT", 8], ["BUY_SEED", "STRAWBERRY", 2], ["BUY_SEED", "MELON", 1]],  # 121
    [["SELL", "WHEAT", 2], ["BUY_SEED", "MELON", 1]],  # 122
    [],  # 123
    [],  # 124
    [],  # 125
    [],  # 126
    [],  # 127
    [],  # 128
    [],  # 129
    [],  # 130
    [],  # 131
    [],  # 132
    [],  # 133
    [],  # 134
    [["BUY_PRODUCT", "WHEAT", 2]],  # 135
    [],  # 136
    [],  # 137
    [],  # 138
    [],  # 139
    [],  # 140
    [],  # 141
    [],  # 142
    [],  # 143
    [["SELL", "FERTILIZER", 5], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["BUY_SEED", "STRAWBERRY", 3], ["BUY_SEED", "MELON", 1]],  # 144
    [["BUY_SEED", "MELON", 1]],  # 145
    [],  # 146
    [],  # 147
    [["SELL", "WOOL", 6], ["BUY_LAND"], ["BUY_SEED", "MELON", 2]],  # 148
    [["BUY_PRODUCT", "WHEAT", 2]],  # 149
    [],  # 150
    [["SELL", "WOOL", 6], ["BUY_SEED", "MELON", 2]],  # 151
    [["BUY_SEED", "CARROT", 7]],  # 152
    [],  # 153
    [],  # 154
    [["BUY_PRODUCT", "WHEAT", 2]],  # 155
    [],  # 156
    [],  # 157
    [],  # 158
    [],  # 159
    [],  # 160
    [],  # 161
    [],  # 162
    [],  # 163
    [["BUY_PRODUCT", "WHEAT", 2]],  # 164
    [],  # 165
    [],  # 166
    [],  # 167
    [["SELL", "FERTILIZER", 6], ["BUY_ANIMAL", "COW", 2], ["BUY_ANIMAL", "SHEEP", 1], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["BUY_SEED", "WHEAT", 4]],  # 168
    [["HIRE"], ["HIRE"], ["HIRE"]],  # 169
    [],  # 170
    [],  # 171
    [["BUY_PRODUCT", "WHEAT", 2]],  # 172
    [],  # 173
    [],  # 174
    [],  # 175
    [],  # 176
    [],  # 177
    [],  # 178
    [],  # 179
    [],  # 180
    [],  # 181
    [],  # 182
    [],  # 183
    [],  # 184
    [],  # 185
    [],  # 186
    [],  # 187
    [],  # 188
    [],  # 189
    [],  # 190
    [],  # 191
    [["SELL", "FERTILIZER", 6], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["BUY_PRODUCT", "WHEAT", 10], ["BUY_SEED", "WHEAT", 2]],  # 192
    [["SELL", "MILK", 6], ["BUY_ANIMAL", "SHEEP", 1], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["BUY_SEED", "STRAWBERRY", 4], ["BUY_SEED", "WHEAT", 1]],  # 193
    [["HIRE"]],  # 194
    [["BUY_PRODUCT", "WHEAT", 2]],  # 195
    [],  # 196
    [["SELL", "MILK", 6]],  # 197
    [["BUY_PRODUCT", "WHEAT", 2]],  # 198
    [],  # 199
    [],  # 200
    [],  # 201
    [],  # 202
    [],  # 203
    [],  # 204
    [],  # 205
    [],  # 206
    [],  # 207
    [],  # 208
    [["BUY_SEED", "WHEAT", 1]],  # 209
    [["BUY_SEED", "WHEAT", 1]],  # 210
    [],  # 211
    [],  # 212
    [],  # 213
    [],  # 214
    [],  # 215
    [["SELL", "FERTILIZER", 6], ["SELL", "WHEAT", 4], ["BUY_ANIMAL", "COW", 2], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 216
    [["SELL", "FERTILIZER", 3], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 217
    [["HIRE"], ["HIRE"]],  # 218
    [["BUY_PRODUCT", "WHEAT", 3]],  # 219
    [],  # 220
    [],  # 221
    [["SELL", "WOOL", 4]],  # 222
    [["SELL", "WOOL", 4]],  # 223
    [],  # 224
    [["BUY_PRODUCT", "WHEAT", 4]],  # 225
    [],  # 226
    [],  # 227
    [["BUY_PRODUCT", "WHEAT", 3]],  # 228
    [],  # 229
    [],  # 230
    [],  # 231
    [],  # 232
    [["BUY_PRODUCT", "WHEAT", 2]],  # 233
    [],  # 234
    [],  # 235
    [],  # 236
    [],  # 237
    [],  # 238
    [],  # 239
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 240
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 241
    [["HIRE"]],  # 242
    [["BUY_PRODUCT", "WHEAT", 7]],  # 243
    [],  # 244
    [],  # 245
    [],  # 246
    [],  # 247
    [],  # 248
    [],  # 249
    [["SELL", "FERTILIZER", 10]],  # 250
    [["SELL", "FERTILIZER", 5]],  # 251
    [["SELL", "FERTILIZER", 10]],  # 252
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 4]],  # 253
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 6], ["BUY_PRODUCT", "WHEAT", 10]],  # 254
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 6]],  # 255
    [["SELL", "FERTILIZER", 18], ["SELL", "MELON", 12], ["SELL", "WHEAT", 6]],  # 256
    [["SELL", "FERTILIZER", 18], ["SELL", "MELON", 12], ["SELL", "WHEAT", 1], ["BUY_PRODUCT", "WHEAT", 15]],  # 257
    [["SELL", "MELON", 12], ["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 2]],  # 258
    [["SELL", "MELON", 12], ["SELL", "FERTILIZER", 6]],  # 259
    [["BUY_SEED", "WHEAT", 1]],  # 260
    [],  # 261
    [["SELL", "MELON", 12], ["BUY_SEED", "WHEAT", 2]],  # 262
    [["BUY_SEED", "WHEAT", 3]],  # 263
    [["SELL", "MELON", 12], ["SELL", "MILK", 6], ["BUY_ANIMAL", "COW", 2], ["BUY_LAND"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["BUY_SEED", "STRAWBERRY", 23]],  # 264
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 265
    [["HIRE"], ["HIRE"]],  # 266
    [["BUY_PRODUCT", "WHEAT", 7]],  # 267
    [],  # 268
    [],  # 269
    [],  # 270
    [],  # 271
    [],  # 272
    [["BUY_SEED", "WHEAT", 1]],  # 273
    [],  # 274
    [["BUY_SEED", "WHEAT", 1]],  # 275
    [["BUY_PRODUCT", "WHEAT", 10], ["BUY_SEED", "WHEAT", 1]],  # 276
    [],  # 277
    [],  # 278
    [["BUY_SEED", "WHEAT", 1]],  # 279
    [["BUY_SEED", "WHEAT", 1]],  # 280
    [],  # 281
    [],  # 282
    [["BUY_SEED", "WHEAT", 1]],  # 283
    [],  # 284
    [],  # 285
    [],  # 286
    [],  # 287
    [["SELL", "MILK", 6], ["SELL", "FERTILIZER", 6], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 288
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 289
    [],  # 290
    [["BUY_PRODUCT", "WHEAT", 8]],  # 291
    [],  # 292
    [],  # 293
    [["SELL", "FERTILIZER", 1]],  # 294
    [["SELL", "FERTILIZER", 1]],  # 295
    [],  # 296
    [],  # 297
    [],  # 298
    [],  # 299
    [],  # 300
    [["BUY_SEED", "WHEAT", 1]],  # 301
    [["SELL", "FERTILIZER", 7]],  # 302
    [["BUY_SEED", "WHEAT", 1]],  # 303
    [],  # 304
    [["SELL", "FERTILIZER", 8]],  # 305
    [["SELL", "FERTILIZER", 7], ["BUY_SEED", "WHEAT", 1]],  # 306
    [["SELL", "FERTILIZER", 7]],  # 307
    [["SELL", "FERTILIZER", 6]],  # 308
    [["SELL", "FERTILIZER", 6]],  # 309
    [["SELL", "FERTILIZER", 6]],  # 310
    [["SELL", "FERTILIZER", 6]],  # 311
    [["SELL", "WOOL", 8], ["SELL", "MILK", 6], ["SELL", "FERTILIZER", 10], ["SELL", "WHEAT", 8], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 312
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 313
    [["HIRE"]],  # 314
    [],  # 315
    [],  # 316
    [],  # 317
    [],  # 318
    [],  # 319
    [],  # 320
    [["BUY_PRODUCT", "WHEAT", 9]],  # 321
    [],  # 322
    [],  # 323
    [],  # 324
    [],  # 325
    [],  # 326
    [],  # 327
    [],  # 328
    [],  # 329
    [],  # 330
    [["BUY_SEED", "WHEAT", 1]],  # 331
    [["BUY_SEED", "WHEAT", 1]],  # 332
    [],  # 333
    [],  # 334
    [],  # 335
    [["SELL", "MILK", 9], ["SELL", "FERTILIZER", 6], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 336
    [["SELL", "FERTILIZER", 2], ["HIRE"], ["HIRE"], ["HIRE"]],  # 337
    [],  # 338
    [],  # 339
    [],  # 340
    [],  # 341
    [["BUY_PRODUCT", "WHEAT", 10]],  # 342
    [["SELL", "FERTILIZER", 6]],  # 343
    [["SELL", "FERTILIZER", 2]],  # 344
    [],  # 345
    [],  # 346
    [],  # 347
    [],  # 348
    [],  # 349
    [],  # 350
    [],  # 351
    [],  # 352
    [],  # 353
    [],  # 354
    [["SELL", "FERTILIZER", 3]],  # 355
    [["SELL", "FERTILIZER", 3]],  # 356
    [["SELL", "FERTILIZER", 3], ["BUY_SEED", "WHEAT", 1]],  # 357
    [["BUY_SEED", "WHEAT", 1]],  # 358
    [],  # 359
    [["SELL", "MILK", 6], ["SELL", "WHEAT", 8], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 360
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 361
    [["HIRE"], ["HIRE"]],  # 362
    [],  # 363
    [],  # 364
    [["SELL", "FERTILIZER", 2]],  # 365
    [["SELL", "MILK", 12], ["SELL", "FERTILIZER", 9]],  # 366
    [],  # 367
    [],  # 368
    [["SELL", "FERTILIZER", 1]],  # 369
    [["SELL", "FERTILIZER", 3]],  # 370
    [["SELL", "FERTILIZER", 9]],  # 371
    [["SELL", "FERTILIZER", 8]],  # 372
    [["SELL", "FERTILIZER", 8]],  # 373
    [["SELL", "FERTILIZER", 9]],  # 374
    [["SELL", "FERTILIZER", 12]],  # 375
    [["SELL", "FERTILIZER", 16], ["BUY_SEED", "WHEAT", 1]],  # 376
    [["SELL", "FERTILIZER", 16]],  # 377
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 1], ["BUY_SEED", "WHEAT", 1]],  # 378
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 1], ["BUY_SEED", "WHEAT", 1]],  # 379
    [["SELL", "FERTILIZER", 18], ["SELL", "STRAWBERRY", 6], ["SELL", "WHEAT", 6], ["BUY_SEED", "WHEAT", 1]],  # 380
    [["SELL", "FERTILIZER", 18], ["BUY_SEED", "WHEAT", 1]],  # 381
    [["SELL", "FERTILIZER", 18], ["SELL", "WOOL", 12], ["BUY_SEED", "WHEAT", 1]],  # 382
    [["SELL", "FERTILIZER", 6], ["BUY_SEED", "WHEAT", 2]],  # 383
    [["SELL", "MILK", 6], ["SELL", "FERTILIZER", 13], ["SELL", "STRAWBERRY", 2], ["SELL", "WHEAT", 8], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 384
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 385
    [],  # 386
    [],  # 387
    [],  # 388
    [],  # 389
    [],  # 390
    [],  # 391
    [],  # 392
    [],  # 393
    [["BUY_PRODUCT", "WHEAT", 9]],  # 394
    [["SELL", "FERTILIZER", 5]],  # 395
    [["SELL", "MELON", 6], ["SELL", "FERTILIZER", 1]],  # 396
    [],  # 397
    [],  # 398
    [["BUY_SEED", "WHEAT", 1]],  # 399
    [],  # 400
    [["BUY_SEED", "WHEAT", 1]],  # 401
    [["SELL", "FERTILIZER", 1], ["BUY_SEED", "WHEAT", 1]],  # 402
    [["SELL", "FERTILIZER", 1], ["BUY_SEED", "WHEAT", 1]],  # 403
    [["SELL", "FERTILIZER", 4], ["BUY_SEED", "WHEAT", 1]],  # 404
    [["SELL", "FERTILIZER", 4], ["BUY_SEED", "WHEAT", 2]],  # 405
    [["SELL", "FERTILIZER", 4], ["BUY_SEED", "WHEAT", 1]],  # 406
    [["SELL", "FERTILIZER", 10]],  # 407
    [["SELL", "MELON", 6], ["SELL", "MILK", 6], ["SELL", "FERTILIZER", 9], ["SELL", "WHEAT", 7], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 408
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 409
    [["HIRE"], ["HIRE"]],  # 410
    [],  # 411
    [],  # 412
    [],  # 413
    [["SELL", "FERTILIZER", 8], ["BUY_PRODUCT", "WHEAT", 8]],  # 414
    [["SELL", "FERTILIZER", 18]],  # 415
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 3]],  # 416
    [["SELL", "FERTILIZER", 18], ["SELL", "WOOL", 5], ["SELL", "WHEAT", 7]],  # 417
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 7], ["SELL", "WOOL", 3], ["BUY_PRODUCT", "WHEAT", 11]],  # 418
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 7], ["SELL", "WOOL", 1]],  # 419
    [["SELL", "MELON", 12], ["SELL", "FERTILIZER", 10], ["BUY_PRODUCT", "WHEAT", 8]],  # 420
    [["SELL", "MELON", 6], ["SELL", "FERTILIZER", 7]],  # 421
    [["SELL", "FERTILIZER", 7]],  # 422
    [["SELL", "FERTILIZER", 7]],  # 423
    [["SELL", "FERTILIZER", 6]],  # 424
    [["SELL", "FERTILIZER", 6]],  # 425
    [["SELL", "FERTILIZER", 14]],  # 426
    [["SELL", "FERTILIZER", 18], ["SELL", "STRAWBERRY", 6], ["SELL", "WHEAT", 2]],  # 427
    [["SELL", "FERTILIZER", 18]],  # 428
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 5]],  # 429
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 5], ["BUY_SEED", "WHEAT", 1]],  # 430
    [["SELL", "MELON", 6], ["SELL", "FERTILIZER", 12], ["BUY_PRODUCT", "WHEAT", 8], ["BUY_SEED", "WHEAT", 4]],  # 431
    [["SELL", "MELON", 12], ["SELL", "MILK", 16], ["SELL", "STRAWBERRY", 8], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 432
    [["SELL", "MILK", 8], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 433
    [["HIRE"], ["HIRE"]],  # 434
    [],  # 435
    [],  # 436
    [],  # 437
    [],  # 438
    [["BUY_PRODUCT", "WHEAT", 8]],  # 439
    [["SELL", "FERTILIZER", 3]],  # 440
    [["SELL", "FERTILIZER", 4]],  # 441
    [["SELL", "FERTILIZER", 1]],  # 442
    [["SELL", "FERTILIZER", 2]],  # 443
    [["SELL", "FERTILIZER", 3]],  # 444
    [["SELL", "FERTILIZER", 2], ["BUY_SEED", "WHEAT", 1]],  # 445
    [["SELL", "FERTILIZER", 2]],  # 446
    [["SELL", "FERTILIZER", 1]],  # 447
    [["SELL", "FERTILIZER", 1], ["BUY_SEED", "WHEAT", 1]],  # 448
    [["SELL", "FERTILIZER", 3]],  # 449
    [["SELL", "FERTILIZER", 2], ["BUY_SEED", "WHEAT", 1]],  # 450
    [["SELL", "FERTILIZER", 2], ["BUY_SEED", "WHEAT", 1]],  # 451
    [["SELL", "FERTILIZER", 2]],  # 452
    [["SELL", "FERTILIZER", 5], ["BUY_SEED", "WHEAT", 1]],  # 453
    [["SELL", "FERTILIZER", 5], ["BUY_SEED", "WHEAT", 1]],  # 454
    [["SELL", "FERTILIZER", 5]],  # 455
    [["SELL", "MILK", 6], ["SELL", "STRAWBERRY", 8], ["SELL", "FERTILIZER", 5], ["SELL", "WHEAT", 1], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 456
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 457
    [["HIRE"], ["HIRE"]],  # 458
    [],  # 459
    [],  # 460
    [["SELL", "FERTILIZER", 9]],  # 461
    [["SELL", "FERTILIZER", 18]],  # 462
    [["SELL", "FERTILIZER", 14], ["SELL", "WHEAT", 7], ["BUY_PRODUCT", "WHEAT", 8]],  # 463
    [["SELL", "FERTILIZER", 18], ["SELL", "WOOL", 6], ["SELL", "WHEAT", 7]],  # 464
    [["SELL", "WHEAT", 7], ["SELL", "FERTILIZER", 1], ["BUY_PRODUCT", "WHEAT", 9]],  # 465
    [["SELL", "FERTILIZER", 9], ["SELL", "WHEAT", 7]],  # 466
    [["SELL", "FERTILIZER", 14], ["SELL", "WHEAT", 7]],  # 467
    [["SELL", "FERTILIZER", 11], ["SELL", "WHEAT", 7]],  # 468
    [["SELL", "FERTILIZER", 10], ["SELL", "WHEAT", 7]],  # 469
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 7]],  # 470
    [["SELL", "FERTILIZER", 17], ["SELL", "WHEAT", 7]],  # 471
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 7], ["SELL", "WOOL", 1]],  # 472
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 7], ["SELL", "WOOL", 11]],  # 473
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 7], ["SELL", "WOOL", 1], ["BUY_SEED", "WHEAT", 1]],  # 474
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 2]],  # 475
    [["SELL", "FERTILIZER", 18], ["SELL", "STRAWBERRY", 6], ["SELL", "WHEAT", 7]],  # 476
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 1]],  # 477
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 7]],  # 478
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 1]],  # 479
    [["SELL", "MILK", 29], ["SELL", "STRAWBERRY", 8], ["SELL", "WHEAT", 22], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 480
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 481
    [["HIRE"], ["HIRE"]],  # 482
    [["BUY_PRODUCT", "WHEAT", 10]],  # 483
    [],  # 484
    [],  # 485
    [],  # 486
    [],  # 487
    [],  # 488
    [],  # 489
    [],  # 490
    [],  # 491
    [],  # 492
    [],  # 493
    [],  # 494
    [],  # 495
    [["BUY_SEED", "WHEAT", 1]],  # 496
    [],  # 497
    [],  # 498
    [],  # 499
    [],  # 500
    [],  # 501
    [],  # 502
    [],  # 503
    [["SELL", "MILK", 7], ["SELL", "STRAWBERRY", 8], ["SELL", "WHEAT", 8], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 504
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 505
    [["HIRE"], ["HIRE"]],  # 506
    [],  # 507
    [],  # 508
    [],  # 509
    [["SELL", "WHEAT", 6]],  # 510
    [["SELL", "FERTILIZER", 2], ["SELL", "WHEAT", 7]],  # 511
    [["SELL", "FERTILIZER", 5], ["SELL", "WHEAT", 7]],  # 512
    [["SELL", "FERTILIZER", 8], ["SELL", "WHEAT", 7], ["BUY_PRODUCT", "WHEAT", 8]],  # 513
    [["SELL", "FERTILIZER", 17], ["SELL", "STRAWBERRY", 4], ["SELL", "WHEAT", 7]],  # 514
    [["SELL", "FERTILIZER", 9], ["SELL", "WHEAT", 7], ["BUY_PRODUCT", "WHEAT", 8]],  # 515
    [["SELL", "FERTILIZER", 16], ["SELL", "WHEAT", 7]],  # 516
    [["SELL", "FERTILIZER", 9], ["SELL", "WHEAT", 7], ["BUY_PRODUCT", "WHEAT", 9], ["BUY_SEED", "WHEAT", 1]],  # 517
    [["SELL", "FERTILIZER", 18], ["SELL", "WOOL", 4], ["SELL", "WHEAT", 7]],  # 518
    [["SELL", "FERTILIZER", 9], ["SELL", "STRAWBERRY", 6], ["SELL", "WHEAT", 7], ["BUY_PRODUCT", "WHEAT", 10]],  # 519
    [["SELL", "FERTILIZER", 14], ["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 1]],  # 520
    [["SELL", "FERTILIZER", 12], ["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 1]],  # 521
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 7]],  # 522
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 2]],  # 523
    [["SELL", "FERTILIZER", 18], ["SELL", "STRAWBERRY", 6], ["SELL", "WHEAT", 7], ["BUY_SEED", "CARROT", 1], ["BUY_SEED", "WHEAT", 2]],  # 524
    [["SELL", "FERTILIZER", 15], ["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 1]],  # 525
    [["SELL", "FERTILIZER", 16], ["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 1]],  # 526
    [["SELL", "FERTILIZER", 16], ["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 2]],  # 527
    [["SELL", "STRAWBERRY", 23], ["SELL", "FERTILIZER", 13], ["SELL", "WHEAT", 7], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 528
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 529
    [["HIRE"], ["HIRE"]],  # 530
    [["BUY_PRODUCT", "WHEAT", 10]],  # 531
    [["SELL", "WHEAT", 6]],  # 532
    [["SELL", "WHEAT", 4]],  # 533
    [["SELL", "WHEAT", 1], ["BUY_PRODUCT", "WHEAT", 13]],  # 534
    [["SELL", "FERTILIZER", 7], ["SELL", "WHEAT", 7]],  # 535
    [["SELL", "WHEAT", 7], ["SELL", "FERTILIZER", 2]],  # 536
    [["SELL", "WHEAT", 7], ["SELL", "FERTILIZER", 2]],  # 537
    [["SELL", "WHEAT", 7], ["SELL", "FERTILIZER", 2]],  # 538
    [["SELL", "FERTILIZER", 4], ["SELL", "WHEAT", 7]],  # 539
    [["SELL", "FERTILIZER", 7], ["SELL", "WHEAT", 7]],  # 540
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 1]],  # 541
    [["SELL", "FERTILIZER", 17], ["SELL", "WHEAT", 7]],  # 542
    [["SELL", "FERTILIZER", 17], ["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 1]],  # 543
    [["SELL", "FERTILIZER", 18], ["SELL", "MILK", 4], ["SELL", "WHEAT", 7]],  # 544
    [["SELL", "FERTILIZER", 18], ["SELL", "MILK", 7], ["SELL", "WHEAT", 7]],  # 545
    [["SELL", "FERTILIZER", 18], ["SELL", "WOOL", 1], ["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 1]],  # 546
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 7], ["BUY_SEED", "CARROT", 2], ["BUY_SEED", "WHEAT", 1]],  # 547
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 1]],  # 548
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 7], ["BUY_SEED", "CARROT", 1], ["BUY_SEED", "WHEAT", 2]],  # 549
    [["SELL", "FERTILIZER", 18], ["SELL", "MILK", 1], ["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 1]],  # 550
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 2]],  # 551
    [["SELL", "STRAWBERRY", 21], ["SELL", "FERTILIZER", 14], ["SELL", "WHEAT", 9], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 552
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 553
    [["HIRE"], ["HIRE"]],  # 554
    [["BUY_PRODUCT", "WHEAT", 10]],  # 555
    [],  # 556
    [["SELL", "FERTILIZER", 8], ["SELL", "WHEAT", 7]],  # 557
    [["SELL", "FERTILIZER", 11], ["SELL", "WHEAT", 7], ["BUY_PRODUCT", "WHEAT", 9]],  # 558
    [["SELL", "FERTILIZER", 18], ["SELL", "MILK", 2], ["SELL", "WHEAT", 7]],  # 559
    [["SELL", "FERTILIZER", 16], ["SELL", "WHEAT", 7], ["BUY_PRODUCT", "WHEAT", 11]],  # 560
    [["SELL", "FERTILIZER", 18], ["SELL", "MILK", 9], ["SELL", "WHEAT", 7]],  # 561
    [["SELL", "FERTILIZER", 16], ["SELL", "WHEAT", 7], ["BUY_PRODUCT", "WHEAT", 11]],  # 562
    [["SELL", "FERTILIZER", 18], ["SELL", "WOOL", 9], ["SELL", "WHEAT", 7]],  # 563
    [["SELL", "FERTILIZER", 12], ["SELL", "WHEAT", 7], ["BUY_PRODUCT", "WHEAT", 13]],  # 564
    [["SELL", "FERTILIZER", 18], ["SELL", "MILK", 7], ["SELL", "WHEAT", 7], ["SELL", "WOOL", 2]],  # 565
    [["SELL", "FERTILIZER", 16], ["SELL", "WHEAT", 7]],  # 566
    [["SELL", "STRAWBERRY", 6], ["SELL", "FERTILIZER", 11], ["SELL", "WHEAT", 7], ["BUY_PRODUCT", "WHEAT", 14]],  # 567
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 7]],  # 568
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 1]],  # 569
    [["SELL", "FERTILIZER", 11], ["SELL", "WHEAT", 7], ["BUY_PRODUCT", "WHEAT", 12]],  # 570
    [["SELL", "STRAWBERRY", 18], ["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 7]],  # 571
    [["SELL", "WHEAT", 7], ["BUY_PRODUCT", "WHEAT", 8]],  # 572
    [["SELL", "FERTILIZER", 9], ["SELL", "WHEAT", 7]],  # 573
    [["SELL", "STRAWBERRY", 6], ["SELL", "WHEAT", 7], ["SELL", "FERTILIZER", 2], ["BUY_PRODUCT", "WHEAT", 9], ["BUY_SEED", "WHEAT", 1]],  # 574
    [["SELL", "FERTILIZER", 6], ["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 3]],  # 575
    [["SELL", "STRAWBERRY", 13], ["SELL", "WHEAT", 6], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["BUY_PRODUCT", "WHEAT", 8]],  # 576
    [["SELL", "MILK", 17], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 577
    [["HIRE"]],  # 578
    [["BUY_PRODUCT", "WHEAT", 9]],  # 579
    [],  # 580
    [["SELL", "WHEAT", 4]],  # 581
    [["SELL", "WHEAT", 2]],  # 582
    [["BUY_PRODUCT", "WHEAT", 9]],  # 583
    [["SELL", "WHEAT", 7], ["SELL", "FERTILIZER", 1]],  # 584
    [["BUY_PRODUCT", "WHEAT", 9]],  # 585
    [["SELL", "FERTILIZER", 3], ["SELL", "WHEAT", 7]],  # 586
    [["SELL", "WHEAT", 2], ["BUY_PRODUCT", "WHEAT", 8]],  # 587
    [["SELL", "FERTILIZER", 2], ["SELL", "WHEAT", 7]],  # 588
    [["SELL", "WHEAT", 1], ["BUY_PRODUCT", "WHEAT", 10]],  # 589
    [["SELL", "FERTILIZER", 6], ["SELL", "WHEAT", 7]],  # 590
    [["SELL", "WHEAT", 3], ["BUY_PRODUCT", "WHEAT", 10]],  # 591
    [["SELL", "MILK", 7], ["SELL", "FERTILIZER", 3], ["SELL", "WOOL", 4], ["SELL", "WHEAT", 7]],  # 592
    [["BUY_PRODUCT", "WHEAT", 10]],  # 593
    [["SELL", "WHEAT", 1]],  # 594
    [["SELL", "WHEAT", 5]],  # 595
    [["BUY_SEED", "CARROT", 1]],  # 596
    [["SELL", "STRAWBERRY", 8]],  # 597
    [],  # 598
    [["BUY_SEED", "WHEAT", 2]],  # 599
    [["SELL", "STRAWBERRY", 6], ["SELL", "CARROT", 2], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 600
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 601
    [["HIRE"]],  # 602
    [["BUY_PRODUCT", "WHEAT", 8]],  # 603
    [],  # 604
    [["SELL", "FERTILIZER", 5], ["SELL", "WHEAT", 7]],  # 605
    [["SELL", "FERTILIZER", 5], ["SELL", "WHEAT", 7], ["BUY_PRODUCT", "WHEAT", 9]],  # 606
    [["SELL", "FERTILIZER", 16], ["SELL", "STRAWBERRY", 2], ["SELL", "WHEAT", 7]],  # 607
    [["SELL", "FERTILIZER", 7], ["SELL", "WHEAT", 7], ["BUY_PRODUCT", "WHEAT", 9]],  # 608
    [["SELL", "FERTILIZER", 18], ["SELL", "MILK", 6], ["SELL", "WOOL", 2], ["SELL", "WHEAT", 7]],  # 609
    [["SELL", "FERTILIZER", 12], ["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 1]],  # 610
    [["SELL", "FERTILIZER", 13], ["SELL", "WHEAT", 7]],  # 611
    [["SELL", "FERTILIZER", 18], ["SELL", "WOOL", 2], ["SELL", "WHEAT", 7]],  # 612
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 7], ["SELL", "WOOL", 2]],  # 613
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 7], ["SELL", "STRAWBERRY", 1], ["SELL", "WOOL", 2], ["BUY_SEED", "WHEAT", 1]],  # 614
    [["SELL", "FERTILIZER", 18], ["SELL", "STRAWBERRY", 6], ["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 1]],  # 615
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 7]],  # 616
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 1]],  # 617
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 7]],  # 618
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 7]],  # 619
    [["SELL", "STRAWBERRY", 8], ["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 7], ["BUY_SEED", "CARROT", 1], ["BUY_SEED", "WHEAT", 1]],  # 620
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 7], ["BUY_SEED", "CARROT", 1]],  # 621
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 7]],  # 622
    [["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 7], ["BUY_SEED", "CARROT", 1], ["BUY_SEED", "WHEAT", 3]],  # 623
    [["SELL", "STRAWBERRY", 13], ["SELL", "FERTILIZER", 18], ["SELL", "WHEAT", 28], ["SELL", "MILK", 2], ["SELL", "CARROT", 7], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 624
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 625
    [["HIRE"]],  # 626
    [["BUY_PRODUCT", "WHEAT", 10]],  # 627
    [],  # 628
    [["SELL", "WHEAT", 5]],  # 629
    [["BUY_PRODUCT", "WHEAT", 8]],  # 630
    [["SELL", "FERTILIZER", 2], ["SELL", "WHEAT", 7]],  # 631
    [["SELL", "WHEAT", 6]],  # 632
    [["BUY_PRODUCT", "WHEAT", 11]],  # 633
    [["SELL", "FERTILIZER", 6], ["SELL", "WHEAT", 7]],  # 634
    [["SELL", "FERTILIZER", 3], ["SELL", "WHEAT", 7]],  # 635
    [["SELL", "WHEAT", 7]],  # 636
    [["SELL", "FERTILIZER", 6], ["SELL", "WHEAT", 7]],  # 637
    [["SELL", "FERTILIZER", 6], ["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 2]],  # 638
    [["SELL", "FERTILIZER", 6], ["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 1]],  # 639
    [["SELL", "FERTILIZER", 6], ["SELL", "WHEAT", 7]],  # 640
    [["SELL", "MILK", 10], ["SELL", "WHEAT", 7]],  # 641
    [["SELL", "FERTILIZER", 5], ["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 2]],  # 642
    [["SELL", "FERTILIZER", 11], ["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 3]],  # 643
    [["SELL", "FERTILIZER", 10], ["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 1]],  # 644
    [["SELL", "FERTILIZER", 10], ["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 2]],  # 645
    [["SELL", "FERTILIZER", 10], ["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 2]],  # 646
    [["SELL", "FERTILIZER", 10], ["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 1]],  # 647
    [["SELL", "STRAWBERRY", 9], ["SELL", "FERTILIZER", 10], ["SELL", "MILK", 3], ["SELL", "WHEAT", 18], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 648
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 649
    [["HIRE"]],  # 650
    [["BUY_PRODUCT", "WHEAT", 10]],  # 651
    [],  # 652
    [["SELL", "WHEAT", 5]],  # 653
    [["SELL", "WOOL", 8], ["SELL", "WHEAT", 7]],  # 654
    [["SELL", "WHEAT", 4], ["BUY_PRODUCT", "WHEAT", 13]],  # 655
    [["SELL", "MILK", 12], ["SELL", "WHEAT", 7]],  # 656
    [["SELL", "WHEAT", 2], ["BUY_PRODUCT", "WHEAT", 9]],  # 657
    [["SELL", "MILK", 3], ["SELL", "WHEAT", 7]],  # 658
    [["SELL", "WHEAT", 6]],  # 659
    [["SELL", "WHEAT", 7], ["BUY_PRODUCT", "WHEAT", 9], ["BUY_SEED", "WHEAT", 1]],  # 660
    [["SELL", "WHEAT", 7]],  # 661
    [["SELL", "WHEAT", 7]],  # 662
    [["SELL", "WHEAT", 7]],  # 663
    [["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 2]],  # 664
    [["SELL", "STRAWBERRY", 10], ["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 1]],  # 665
    [["SELL", "WHEAT", 7]],  # 666
    [["SELL", "STRAWBERRY", 6], ["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 2]],  # 667
    [["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 1]],  # 668
    [["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 3]],  # 669
    [["SELL", "WHEAT", 7]],  # 670
    [["SELL", "WHEAT", 7], ["BUY_SEED", "WHEAT", 3]],  # 671
    [["SELL", "MILK", 21], ["SELL", "STRAWBERRY", 19], ["SELL", "FERTILIZER", 11], ["SELL", "WOOL", 8], ["SELL", "CARROT", 2], ["SELL", "WHEAT", 5], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 672
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 673
    [["HIRE"]],  # 674
    [["BUY_PRODUCT", "WHEAT", 4]],  # 675
    [],  # 676
    [],  # 677
    [["BUY_PRODUCT", "WHEAT", 3]],  # 678
    [],  # 679
    [],  # 680
    [],  # 681
    [],  # 682
    [],  # 683
    [],  # 684
    [],  # 685
    [["SELL", "WHEAT", 1]],  # 686
    [["SELL", "WHEAT", 1]],  # 687
    [["SELL", "WHEAT", 1]],  # 688
    [["SELL", "WHEAT", 1]],  # 689
    [["SELL", "WHEAT", 1]],  # 690
    [["SELL", "WHEAT", 1]],  # 691
    [["SELL", "WHEAT", 1]],  # 692
    [["SELL", "WHEAT", 1]],  # 693
    [["SELL", "WHEAT", 1]],  # 694
    [["SELL", "WHEAT", 1]],  # 695
    [["SELL", "MILK", 8], ["SELL", "STRAWBERRY", 6], ["SELL", "WHEAT", 61], ["SELL", "FERTILIZER", 9], ["SELL", "WOOL", 4], ["SELL", "CARROT", 6], ["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 696
    [["HIRE"], ["HIRE"], ["HIRE"], ["HIRE"]],  # 697
    [],  # 698
    [],  # 699
    [],  # 700
    [],  # 701
    [],  # 702
    [],  # 703
    [],  # 704
    [],  # 705
    [],  # 706
    [],  # 707
    [],  # 708
    [],  # 709
    [["SELL", "MILK", 9], ["SELL", "WHEAT", 2]],  # 710
    [],  # 711
    [],  # 712
    [],  # 713
    [],  # 714
    [],  # 715
    [],  # 716
    [["SELL", "MILK", 3], ["SELL", "WOOL", 4], ["SELL", "STRAWBERRY", 2], ["SELL", "WHEAT", 10]],  # 717
    [["SELL", "MILK", 12], ["SELL", "WHEAT", 10]],  # 718
]

