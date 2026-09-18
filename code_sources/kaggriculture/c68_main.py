"""C68: refreshed THUNDER field route plus adaptive premium preemption.

Field and labor actions come from the stable route shared by the Kakuteki and
mrgrishninsb top-scoring submissions.  Runtime logic preserves the public V23
actor-local weed repair and nonlinear price-impact SELL ordering, plus the
terminal shed cleanup observed in the frontier replays.  C45 advances eligible
premium sales two turns instead of one and tracks independent repayment debts,
so consecutive planned sales can be shifted without changing total quantity.
"""
import base64
import copy
import json
import math
import zlib


_ACTIONS = json.loads(zlib.decompress(base64.b85decode('c-rk<O>Z1mlKd|`_d)D#%GBOysb@_LZ3+~%jah*(49qMRSj-;0dt1zZUs~*ss(O);k@>Q^X^l^&Np;t&_mM9@A|k*1-^G9Y^6TIK_UpyJe7X2|^Xb#Y)8gVkfBEmf{?GF-o`3xNFTeiR-~RXc=PwsO+&*lc|Em4){pY{@eDl-ok2iN0i;MU7+l$3z^XpGPY&IV+7VG^VK5aH1o`1dlVRQ3%vACN2`p3=P{ZE5me|)(A@cI4Y@B>f(Sd3oh_Whqfe;hpj@M2#swwq6nUk7^lVfXTbj}6E7^4H;nSP$EcX8gFH?jIh1`1<X~pV|lRKB_%%H*obK-+#Wn`|$Jg|2}@+Es^_#=||-Exx0D4In19nd%KVPwo;=9J^$gS$HVFy5B$?`<4Dh&d}6pUZXP!e)`Q;PsB^dbmvGAV?=&4RcqW^&$zes`dwiLmeb7GX_`TrxBv!wDz~O7{xr(oP`<zerpLg>Orb=IJdo7Opww<Z2#U6~;o}!w?KA6gOib@t+nX8J$mZq$0(f3~hW@_?Ex$ix0SMyi7FK(Bhb`P<cso6vOZ`<6=v2~P*nrr7weh7Ro^55Kh>Sd#{tL^^oZu9=}=Ra*89&hh%|NZND+lwyby1Wb{bf2POkT2L9+t5J4Q{90&vlATl{&-g|(C#}k7iD5o|M8JOKJtn_GPa4IHg~^8qJxw25@6zhwh1}kK82#dgAd?a9y>sR(PGAwH8I?HYTyfBJ_T(}bNS|PhvV&-87Q#-aO}zm?Yjhz(f@ceO|FsOI|{|q1STKPQf7eDNFuZe2BBKw(d`5$hH#wVW(4y5f@L!%*c~7XXA`Eh!cQhXusTEFOYsDCx$*xDpUqx%qdRY$l)aq%`qSgX&G!4v!^2-L7OUiCIQgOcQmncj&vQ}sUYYxVb+A&sZz6?a3y?}pU#a@N(GIRPYj{Sw!>Z}^+jUQXxQ|}M6)(^vU86Gu77-;_{a8}*kdE6U^?k>InTh!#H`8)GG$*9>7nGD@-rX}ZQOQA0@^L*^-ydJ{Wrnn1)Gz3Yc!^D%R)7Dv`>Vp`zQG40!sM8n_&FJ(8G-a~yZ7ed-x3!Xm`rj_q>~N-7YBSPDA8qt<Y|a44QFTIwe5V4MbJa;!|0?JKmKbRfw$Fo@6CmnJaRfncz(E*l?Blw^0urhuaZ;~%e?cqe|7II_jg~N;ar$+V72t<f8B?^%127m>wg(>4mwf}$Vc!)Fh4x?J*9q!<J=ws3NTOLE)YPQ?Kk*V+rqBZ&a%A|)!Fuqu!RQj=2?A*)>k;*mxn9q<%hmQH2vC&w2qM#IYFj75Q?*!Ku;*HX3;9KFEw*oi@=%%#?=Q!I?)Q8GpVqOClwTD9X#fBIS0dl<P?4Z3pd<&(#}JaBvIn`U!eTJQa~)PQ8n=(@+?n)^ngxKZ6ogn=oO?BO#L=9@63@2_#W-o;EmvZ(T9iokIp_I{?##(yuZKOS!!UxSNrhq`QrI-;rn)NwgEl5jXsxJ^tmGhEuVBR-?bF(M1$lM@C{^#n~XJ;{%9AWO***m2x^ZYbuk7)cfRBFWxG=%UpMk4-N_+7o02tICQ}n%KfE68prfmf@)w7{Myo0-e1uqD=UV66^_FPVpF;QeI6BAQ>(^h-UH@6gh>r49j+w+*2=;X5%m;AN+}SxCo`7TIZ!7f5GV-LvrwY6Fjjb^OEL|}N@eA5&&SYjdLU+EbRD&(SlY$URiRxC%u$np~3#YIY@DPv#Gu_M1S#qPqGK>#8RjpS^kwtRiXhQ5l`xT_p<Vsi*9~7a7!7NbtmNBb+Xk&XRV6Ab{#X&M2V_Mq*Rj*kUm(B&*s)j=mGh%2JDiX8EIJSOv7xx$>b^s5&hSLtdh2=dLHQ7uSel6^vs<tky{7{*peLIMjjuA^`e6+wpNo7TMuuq_@#wh4oQqPp@kqm>Rr5PkGb!S$J0*>dbounQ{tMRy@$(}}?!UeW`DqzQ^gSJiv7mmJKXKj|qhSZ~vo{;H#pwJ|@DS#(RmH?uOX5JfMVw!O^v9o|0lQ0Ku>@;<SOtUhyA3_|i#BX?lBE&f*{0E+$8NtM!<t(rP*&l6o1<$5=(ZsVfT}^*mvBCk0IuG;D$en>_6olNHc>35j6gYY`L)@GZYrn2d0v$)8Y@w{J@@5}_H7X#Kbbn`NTXLAmO;O{U54RD~^r-=DD(YG#Px8OF%>DoI_U_MP$A1_QT)t@|g3IpONtd_343tUY#E>ZHb(y%gJvTd7_z+6>k`o>Cs>=)hwD8e|Cs{?^O<*!z*IP~X6d^i*OAaDMx89q9eM~lOjHfUkPGoBiXrkRfzzF@33felGX`qnVD;+FUv+QLLB~vK_zBLc5ol;BUyr5E_xM};h22wp?krUacd?QTrbb)C>WejImGE9>?HAu<~m=!Oa1r@Orjk?|4Es!V2UiWobuz;fyC1nLKo5v2nn*>UE-8cBucDv7jcqh-F=+n$Z=vp|MHS;~TGGI7wVPc2ivT71X7-DfWGTS7S0M5p^t+ymJc~=={nN<fn&T2o)AUNBN>&g0YT0XfBh|koeX76MJ$9vfT9s<mEem!=Zi@e+RMW@~AGT=V9pbQFdD0`RIvm)C$7ALycHCB!jC!jC%bkmk_^B_t6R`Xk1G>|H(3T-19fAq${hcyU1M2I|<=yp71E7jkeC3gd|LIP^hFjIP+I_RCbnFZ!@z)jgMxDJbNt27?&4p_PgvjT&x@JNAiWwp!78WWmd3)RzXt{v3{ZURc9;?x(zrJ8n~0iM=(Cir9hl%frhLbimE<TyFfZ9%7C1D*+Azsavb;(>rH$&g9XD2WVR3duBx2@BOzV;%rIw1@M6pu&?R1K;@((L4?DiOdcGPY2&XLN*6BCAK5zgtF5F3Ks~YyMM2j<?CITz=qV(4EFV-Q$gBx9D1IBDM)LLd!YTZaH$KPr;{}amQV5aMph)}<&zH6d$0l|ClP%+XB)P!#XMXWt*igT&KC>3hE$Rdl<Sp+>RbcTpyp&h)Swb7NSdci_Q~l#M8G^RC;~(Pn>59=0OKkqqlEf*F2VNU_Fuz5332eJ2Tw~bN?RT$B)h)XU<tHts0AE#BEHS+TDl!+RXQNEBBX`ULPvl;!I_&I-_6kYl%1^2Z^gEivH802Xma1Ox_`SrM$c{U4;wa{D~yZa5P>}DW<I)7Sv-{zI!e|O=5+2@+(}X@!1e%J)vc7r*Cv~m719c!#cd$~{1kwvqMpZ|;|m7jK?H)wfCaYh@R+U*h;;lj&<6gq4U7D6%Gn`5w3A^5jq?FC+*Hg7#xM`G{nZAtBQX84g|b}#&LUfiX9;OI;t&?p(~v}?7{ea^*>D+_=3g%LAou!7k(YE;Y2A7`t?_RvVcoEPC{?|sp`C;%pkQfvXx33Bk}=_Eon274h-|6s`$)W652A}+5jt6i&yA0w7EQo2homVKK3Yg#r!#{fQY<Zyt{v9Kx`EkR-(VyvaF@Bwkv47#(aw!W#r8y;gaCG9Vm2_+M}*UxDS${@S$o3~Uahj!6t1+Xh-<g(%>fyjN18F%yuQ`i<sF?*O<Pn+u=ER8kVuVXt#T9`T91ZypDyIs12Hd%fYcc4Pshx?v7{%sJd*5SdPiVW6L0=wY2in>I|D+9xxlm0(plYDEA;lv+K96*SA`d%SniZRv3%-bxW9@Z`sGd5fC#cSc<b*5zwfIh&k<I8q!5AH&{G~(1+tX-@SL2CSUt6@^eaUR#e%`*Qb-~4d|y>>)@rWW|6=aqZK_9rw8<iz1IYfEF=gTFNr40gi@!UzSzA6~Ak!>nAh5^CfFy|h9%9m`?$0=N46X{o0iR669-k8z$?=q;<B%}s9eb0;Kj6&AcBf6^h=pXt{dX|f02iI@D;ucxQs+G3fHTitz(lt(Loqd8;iz|P(&SiF8hb?faW#Ln%GOM4^sErUeD3j8_OU$!GS}1#8<seS6e+;sU;mCGvNGK=pmf+lsE1X|6%%PWJ!760-V&K&)}tcF+C68$1|kd%+BkRUW*5layIhY=1O7}z6-}Bi8s2pl)msNVvNKiQ>TD8fB&f3+eS~)6D&3<G9hlHIq{)dC$8Z?$*u@GT)QhXQnc@rD?3~5OYC?H12OpXs+nr-Ob8j!A*M<-eiv9@M2p!6DwzY<kl5Q1*kaUQK>;}Ol%Uc9=2dTK6S7qeJm#k)LVrYUUa#PsI<YZt>+byB4T}>shG(d%wvR=Cn0{Kie&n}e(siOX+(VOKUt$A388lRK^%DFl`cG0)jxFlE;lfDiyxwhfXrKwDES%KE|D~c;YhTBR(hKZ&S4+xW;u{vUz5;t*YbWw0^OtRxm0&EU<Qb<n@5X;<~enzfeP)=wTBMAS^CeAD?^P)YJop<FxQ96{K=CIX>YmOG}+v&+f1p$Pi?n%VeBP{&+w8~{1uY*NqK-L;SI%6@C^#|cZV9U|Cf<pPx2+EJBeIgij#8~qK2+a^w+c3z%$hR650>&vs9}CP%r@Z|gSn8sAmf0P{=iv~O3ITKh5QrS11YLqJ(MO~v$*yet=Jj&w9iUABrm|*<Yr-doyCn;~?I>r<2>7e8hC90Aea)|CjBa&TRf3veY@zuYHRWsW(%m<R9BF&POh5x4+zSx4jbyEItXpR%7JLYyZJ%pJ)_e2$#;5}?&lXOXDzOu&?kXR0hYH9wC|<jQ>@j39ViJDp$_?e$qAFI(|F>DdBKKAj$Eq%B+n#N(sGS}389Mq#OW*X4oLj02zCf-bE|nT$n)ZFAbg87tPY({U^DEZV?k-Ycq*N}JGk|y$Jb4w`?ow$oSj}p)Tr^Qq!KsvXS~5})7|4noc6X0xvGz|;0J-{Pa^Q?*;8T~S?G;3kL|_FZJQSM{GYTiYdjeUdaF@Kpk(Lsj+%#iNv+y2b`3JqnAj|QHcYarfLcs$qBCW|K8TzC&{VF8Uj?+&px3k}0f*EMLFeqCHc3W^tJ(OL+G}5G;Fll`!Ib&KkLJ57#M8@Er+z%bwF|o5AZh)v0Ef}|6*TrN?X&V7m(BpF{40o6ai&D$kG<PxE<1Ns==?rx?*C@*hGe3zJIW_;`@(Sd<zB5Z6-)M)z`LbMdP}ONB$Sjtb+kAI{E%g*t0*Rt|Lek*fI8y?ra2L96v{hv}24=BcY6tlu^n9$zH3dK{o_B2&o~2jnfVv3f>70O;j+YAY(49N1JvFGaPm@rP)FR}Q<gjt8j*b*)IxeUzZf0iPDx7Glx}Zut;f11tp3~=+wsZtg2VH>7TaJJx08zx#l1ChLz+2g+XaTJ};31Zk_Po<+5yGUP33Xcgw0pw2gw(Cfg#ehuyoDS3P0At+J&<=RO|pO;MHkJrFNIj3_6L%j;O8KeweRZ^q0}I^fo2s%D6R~YN@-<83Ei>fmE)FxEjDI_HGWh!hol+T!bwJWm^ac|<f2h%i&!>Aks_%Il?j6e0ggIdnDdPKbdnSdqh<cBCUNu5!X*s>OCUEr%ICaklRsDA2Civ7s!)%xKWYe!GC6C5$t+8qY9jukVw?cdsAm|Zh5famb#adhqzU?^{z()uZ*w!?6~Ra$G6fFFTn3gG_6Pv{r9hv)aOu>)v^eY;FNV}60GtZSIm%CaxRC(I@ubl~3`NsJtx%F`?BvH`K)yiZtZ^aQM6786Z~LX`16I(k0*pT@Qjo+5^<0c%oyAFGYSFGgPDXm-cU6q%$Y%2tWGIJv$zjg|@YDnY)$IIW8%Q1IONCn^w_7`AuJfZ=8D4d8CBRb*Xm0IXE5pf_3U)f#{g3LE8UVw#6QNW5nQw%#wvAeIi<~k%#SzKyAtqAev#w?obv-qD<#moKL^!*AD=^N6S)6sZqRXo%oSguC(?v0}31zgVZScl83oA)BTXjNq;A7wV_a@g#4YVPsg7w(CsZl_G7`t>H>`$w)s?3hqJkBEipB510iKE$bBC#CzO$$m|P72^49x_|?ZXt3IDQT_811g50^BAfLi|J&MRp-W5CxH=Zj4y;MlEUy<0&6y{8p=Y9x0OTpiO0IcwQZejB0;Nk<p*SZg@cMiD8|y<+bHD{OLowZ_Hdx-MQdP(MnTxnOcbTBeWS#pW%9v{p+i$_?a@!J7U~Z~#CvIKM9j{nT2clW!~r8h?saLCnSM<z|5S6gn8rHavy9Chz)cY~Un=XHZImrb7)M0R$?Pk#w61cp(rs8WoB?U=BnA}ZglIIxbBcID{7X5t@nj}lDB2+~q7W=Dkx7XgyHK(!VdLD-cD`{h-Hj$Wb*rWfm4UW8e+cVxy?H94?wJs<oeO;Zty1?CC9Cz@6Xh98dLao-k!UK;&Olan8<j~uteDF<ASn(95u_q+Q><U9NNEbb$lU#OnG%OGN1W@VbSx@XtvcA+v}hGeMCFq&&U-sl83C9kb^Z#J=79wv-fl@>DG{R9`~s{wg|Xp~-*=u|p^tNPtm4KsC~t<Moj9RrRW2@^ZFfwo9V!Z>k8EVeimW8&5g0uXRiHgnL=W5x-L(<}g+C4-0mwmAn%l6R;FTO+R5(QD{49G0SeJ8&i$v=;p$M5@3<TrlXF9@I8M+C9d+1dI;iOQVa)z#b*_NR#$U9BYN(RXexV_FfzQA_b;^3x@pw%vGbj47>v6@@-gjrXT#Hr@&Y2K(%6v61Vgv_hs8Wvi$N^+TnZh798TuMidiUDYN5pXF{D5B(yWv(@%^>-L!`)(wvBg9IIv1HgnOL%@EnH6UZxjKa|562dAlDt!2S6?(=Wg*$}j!U|A@r)A;)Jr6V_)SZPP4{*+|Mb`a&(^Zfbgo1B8((3}{8ZSbMFUmAb`<Q-@`@cvP&o_e$dOQgG(ZwcN}qB1tmcOiV&1F>NULsda%c%}NOD*vfR;=WQ%4&SKVPQRdL7~XeBYc6_Jmvyh2S!5ORU#j1hc8S$GM)%1F%#DEZPY+wb}*+v6w)pS&zOW*UpL<9>9Sh9cG0)i#FMHaGk7&#0~ZX$TsL`V-0da@N5Jn{H8PT!XX#h1G$_%&dT$kQHeG?yap#lw*ox_gHr9BSi@jageaZk|NZCNyAMA<yXlXgNjFMK1)aC5uzZ|Yhqt?%_nV!^ZjDg50zIKaSLmzn20^1H{|I%@l5DWczYWVvDTwTY^%6P-YQ_{y1#lL@A$j}Mr)DRRUunHUNbH5SKis74Xo+qmxi+ThxcKbSb}MXpy)LtYI)NvkGQQ&4hK&F=X(g=N@dGFwcVyv0mgSGy3?ZP#e%CaIL|XN44X*9)mME*3y%0ogEvlBS&D;^S^p?X{gEG^E*yW<%CVxp%RW3$%ll(0z1Uxr1j0nnGCPoL3cc`juW8$b?qQNZHP|}Fd6Ne{Ju9w4`g}BNFqz0&*NF1z7SHi7O#kKKCRQZ+MQiM;h&(C(lRJ`?gUOFBFwLPL4oRIDh9;n6geVUxUq*S$4tj0XzLb^zqofB6(ycL;oMrbtpeL1=AakkXjMVUMGGSrqXfZ(xI+chX=NcKIhPUID%MbfAPmrI~4wY%GCCcrrMjTKCi@3MeqrlC+aNY7+2MnC{%F@?=VU?OiK8d{+yfk^zT#ePU&Bt23j5jYzU<EnX`DNZ{YJxSC#E&|E{!%{Ot*H7JPi|Zym@y=3NUvWkDA#CKE)A#C1U91#3TfeB+m8TUXNP&r(Uh7`X*DZ;msPm(`twmy8yr}G7j6pg}^o?e$SI4@I(X<i|OT4n8{*KFl3XmeA7UbcPZApXi5mtAsHgg(ra$5C`>HnrxymTCPL61Oo%p}RLe!Z)dxUhF-Rh7W@{3>NpSsRF@wnMGp74nbAq*0nOID9r%1y+Owo&DLqH_f8THFp&PNkp%<@imKU0J50T$*@pi8eeKC^kNitLCz0(bCMnj%8dmy{VN)HvXzp=Z8!@*s=O3Smj<WSGcZb~!!;;GG^=9044CIev?-D_l*qyi0GR6<Ls6uWbB7US6Put<hW=t(xwXgl5HJo0L(S%wf~I|;sL5vSvh}uc2uj3B1WF$il9B~vJS??(s{^m4>2TwQxXn-!FF>_zBSt#f3ucrI$%3(0aq_N^oCbdha**BqvF7U-;B)mVVN%O02@Z96^{w*kX6@{_R@()v1dx=bC2wU8yYFtQMdTuiMNKPx&;r7Q;R8I#f=t6RlS>6@k$}JyT`nC1LEcKq80c6N1`ZS4M(BlkKr*k?6+v6+;RtCPk2WS(;i5%)R3qx4$+xedljPOrm7Z16flpW6c~^%B#t@+3S2UkP$Vk@fu&gN@rc^MXzzZJ?QDGD$ng}N9#??_+>d+wK=Cg%(FtRMUq>kcYY&3jNhw0c=(gS$l24<ycmW$mRNvZw?$iHqp-jz{dUwYo(rH?*iJhMQ?7~Xt>@JAeGsV04y?PD7jSRC^{3`_P%uS2{hv0=H#qYE@T4UiVl?aP{|IQIi()w%f0xHC%{YpNzO*m04|dgRP~k_^FcP;Ju2E5S#^0+T&4!GOIIAMGA#@O@*5_Z}rEmWFE4U`(XSi!;<31EK4U>4uA>f*uijBKWt~?E64HzfLmd(pluZ6@J%cs1>RpS=G)1ds);(APrO$K!j8O1fcp>wDadH$<NKjTbxOBe<jK`=&(SFmLrlD9aKk@NzhaOQ4Cxsf=?0zh><si1_38V=Yb$LjLu^jyka08gcat1cR?|DMe@tJ1H(BVu~?}o{i?z(y;K_tpc9(cidz1xXI(8e4sLG+3+EwI#I_MW*`*{CthmJ<t1=sqG1LIHMh+B36u$|!e#m<C0%2IBpApq-dzwOt7IOb9iqOJvf+v<GPgo}jGFsGWl$sj1?neiSn$gIIQo%qw(rC%bpVMBz0gDB0VK*!6r&4pTlS6_DJh}+6STG;$u8<|?sUZaEgsdUgnV4Et2pA3T4(f`BS?G>}7X_h4Ex8G?DbNMWaYtc+Xm2VN_F@<ZR0FwU?D3NimLaER8J3@lTw6@dr3A7{i<!UH+)Wk8DkMY|OVjumD>qH!_<_i>tey&_tF{Wg$N6^*g4M;-1VY(DINDT(Wf62+`sW;qS8WWdR01s315=g6l@(@X{UV*L9$W+4nHnWS(8V0Td{0|MM`24$19`4x0obcppKHGXRe3I^kitc7g3(A8K*<kdyP!H?-VfWjK(n@Mb(m#KM+vC5up>A=c!U26AMc}_GDJySQZN?&lWMQKimRuTaF|pg(YzI!6%FBhGXi2<iJrYUWx;d4n+y4EgHh;1?RU4QAm(@}zSbT#6!DuNkTu)C8?c13eQ)hdYlBcO&@}joS7iEQ>|$YnH_Zenrh|<@ya(24Ac(@-&)CeU^1Z<BQwo!jVlm4h(gYGgKbGjE8Q@@2BIdmT<r;^p_+?j$j<6YUmSaU?Cvzst5Ov_2BRs_xzP7iTb|Qra1R8=-lOW5$wn>tR8aCl|LF$#}j;FthFP)O{VhLeMu1=ARBQH>^6Su6_iCexBp*RS{KO>2A<>;`v?GOp#%db*FW)??#dql;|FbbL%lBk9JG;f<ifS)J6&n&4#(orzpuuF~S>Xo96R(wq^MMDCVwF+doOP{*9@jHvvG80{W9ihJ_%}aGs4sA{f8ZFFzTMl*yl&sxlxRalgwYR}=v4BO6nq#vWV_mX7d%!UTQI;qB=?8Q6KIbWNwUW>)4BqZ<inD6ziWI$D!Hsp8`)=`tqPX32CuCz~i6lX*G1+8ck_~VUR#?%$KnR`5pMxD2kyC5gw@r-h!8;->RP{pn%JR83Nj?#=qf`jW!No~RoD@MK4(ynjlzh5^X@PYO`RP&+YQtAn%cf`AbsKq_)UV4ozel0+698Il)u0+gOAR?$mIu<x|0R%<SR=Jgsq!Rb1VNU0Q+lP}X2@aXsyr&HgKG4|S}KJK7<2}CdZgkY5Rn`;eCN(^#2YB?R3<ivleS$#8p;dQDe8Bd+j`&zR*Gj%+tW_U0|BZ7cY{>N97N06;$E>~S|s*lm3^EYa7z2m5=VeaAcmmq2XAH_;VPZ2OKa%-CoRz1>L)Q2e0nk&OdTh<v9wT>qFtmkbxO-v&(}6|gEmOz3^S6kjkL#RAhT@1s`*XX5j)&oJ0ffqDl(>@1jGi6l=a(^dR@7upGL+)0PjcEf#Hy_^<5jaUcI4Z(?ZExVD%XbF3K_xM*(&eg$lZ(NOrkXt2H=Jx7~zz>zSyCf|t1skaX)qgNeZfxhRnh;*S}kc(YyCIo2(-To!l3Q3eZ(CG%Ni%}FbX#>A<Xog7^&tMl8((!V>}eH3|s%E1Mnh;AktS@D9V($_ZE>c-LdWa6^~J(wE{SB3Oujc&lufMVFqNY9Z(fsD&Hhv#lOz|dIalq}J@;6mGlQ?r%qu~n*%`SJoNKqelR56%nr-2o@sAx2PF&{(oFIA8)y`ZteMAVsMgPZ-Z8Vf!%o!(gnKdH;7wFB0wdmk%-!&U!`V|EN4MD+UYT)%M?5FHB!xDI-&t5g6>#Kc4;{snv=t')).decode("utf-8"))
__version__ = "C68_THUNDER_ADAPTIVE"

_PRICE_FLOOR = 1
_DEMAND_ALPHA = 0.25
_MARKET_PARAMS = {
    "WHEAT": (25, 10000, 400, "sqrt", 0.8, "log", 0.2),
    "CARROT": (35, 10000, 450, "log", 0.2, "sqrt", 0.7),
    "TOMATO": (60, 10000, 200, "linear", 0.4, "sqrt", 0.6),
    "STRAWBERRY": (120, 10000, 100, "sqrt", 0.7, "linear", 1.6),
    "MELON": (250, 10000, 300, "log", 0.2, "sq", 3.6),
    "EGG": (50, 10000, 332, "linear", 0.4, "log", 0.2),
    "MILK": (160, 10000, 122, "sqrt", 0.6, "linear", 1.6),
    "WOOL": (200, 10000, 105, "log", 0.2, "sq", 3.2),
    "FERTILIZER": (100, 10000, 200, "linear", 0.4, "linear", 0.4),
}
_SHOP_PRODUCTS = {
    "BAKERY": ("EGG", "WHEAT"),
    "PIZZA_SHOP": ("MILK", "TOMATO", "WHEAT"),
    "BRUNCH_SPOT": ("EGG", "WHEAT", "STRAWBERRY"),
    "YARN_STORE": ("WOOL",),
    "ICE_CREAM_SHOP": ("STRAWBERRY", "MILK", "WHEAT"),
    "PET_CAFE": ("CARROT",),
    "SMOOTHIE_SHOP": ("STRAWBERRY", "MILK"),
    "FARMERS_MARKET": ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY"),
}
_SELLABLE = tuple(_MARKET_PARAMS)
_LIQUIDATION_ORDER = (
    "CARROT", "EGG", "FERTILIZER", "MELON", "MILK",
    "STRAWBERRY", "TOMATO", "WHEAT", "WOOL",
)
_WEED_STATE = {0: {}, 1: {}}
_WEED_REPLAY_STEPS = 8
_SHIFT_STATE = {
    0: {"last_step": -1, "debts": {}},
    1: {"last_step": -1, "debts": {}},
}
_PREEMPT_ENABLED = True
_PREEMPT_FRACTION = 2.0
_PREEMPT_MAX_BATCH = 30
_PREEMPT_MAX_CLONE_DISTANCE = 6
_PREEMPT_MIN_PRICE_RATIO = 0.0
_PREEMPT_MIN_FUTURE_QUANTITY = 4
_PREEMPT_START = 120
_PREEMPT_STOP = 680
_PREEMPT_HORIZON = 4
_PREMIUM = ("STRAWBERRY", "MELON", "MILK", "WOOL")


# Online common-route opponent classifier.  Premium products cannot be bought by
# the field route, so their market-inventory increase identifies opponent sales
# after subtracting our previous sale and adding deterministic town drain.
_ADAPT_DEFAULT_HORIZON = 4
_ADAPT_MAX_OPP_HORIZON = 6
_ADAPT_MIN_EVENTS = 2
_RACE_STATE = {0: {}, 1: {}}


def _planned_premium(step, item):
    if not (0 <= step < len(_ACTIONS)):
        return 0
    return sum(
        max(0, int(order[2]))
        for order in (_ACTIONS[step].get("market") or [])
        if len(order) >= 3 and order[0] == "SELL" and order[1] == item
    )


def _town_drain(step, shops, item):
    drain = 0
    if step % 4 == 0:
        for shop in shops or ():
            products = _SHOP_PRODUCTS.get(shop, ())
            if item in products:
                drain += 2 if len(products) == 1 else 1
    if step % 24 == 0:
        drain += 1
    return drain


def _race_state(obs, step):
    seat = _seat(obs)
    state = _RACE_STATE[seat]
    if step == 0 or step < int(state.get("last_step", -1)):
        state = {
            "last_step": -1,
            "inventory": {},
            "own_sells": {},
            "shops": (),
            "scores": {h: 0.0 for h in range(1, _ADAPT_MAX_OPP_HORIZON + 1)},
            "events": 0,
            "horizon": _ADAPT_DEFAULT_HORIZON,
        }
        _RACE_STATE[seat] = state
    return state


def _observe_opponent_market(obs, step):
    state = _race_state(obs, step)
    current = dict(_get(_get(obs, "market", {}) or {}, "inventory", {}) or {})
    previous = dict(state.get("inventory", {}) or {})
    prev_step = int(state.get("last_step", -1))
    if previous and prev_step == step - 1 and _clone_distance(obs) <= _PREEMPT_MAX_CLONE_DISTANCE:
        own = dict(state.get("own_sells", {}) or {})
        shops = tuple(state.get("shops", ()) or ())
        for item in _PREMIUM:
            delta = int(current.get(item, 0) or 0) - int(previous.get(item, 0) or 0)
            inferred = delta + _town_drain(prev_step, shops, item) - int(own.get(item, 0) or 0)
            # Remove the route's same-turn planned sale.  What remains is the
            # distinctive extra batch pulled forward by a preemption policy.
            inferred -= _planned_premium(prev_step, item)
            if inferred < _PREEMPT_MIN_FUTURE_QUANTITY:
                continue
            state["events"] += 1
            for horizon in range(1, _ADAPT_MAX_OPP_HORIZON + 1):
                expected = _planned_premium(prev_step + horizon, item)
                if expected > 0:
                    similarity = min(inferred, expected) / float(max(inferred, expected))
                    state["scores"][horizon] += 1.0 + similarity
                else:
                    state["scores"][horizon] -= 0.15
        if state["events"] >= _ADAPT_MIN_EVENTS:
            best = max(state["scores"], key=lambda h: (state["scores"][h], -h))
            state["horizon"] = min(_ADAPT_MAX_OPP_HORIZON + 1, max(2, best + 1))
    state["last_step"] = step
    state["inventory"] = current
    state["shops"] = tuple(_get(_get(obs, "town", {}) or {}, "unlocked_shops", []) or [])


def _record_own_sells(obs, action, step):
    state = _race_state(obs, step)
    sold = {}
    for order in action.get("market", []) or []:
        if len(order) >= 3 and order[0] == "SELL" and order[1] in _PREMIUM:
            sold[order[1]] = sold.get(order[1], 0) + max(0, int(order[2]))
    state["own_sells"] = sold


def _adaptive_horizon(obs, step):
    return int(_race_state(obs, step).get("horizon", _ADAPT_DEFAULT_HORIZON))


def _get(value, key, default=None):
    if isinstance(value, dict):
        return value.get(key, default)
    getter = getattr(value, "get", None)
    if callable(getter):
        return getter(key, default)
    return getattr(value, key, default)


def _copy_action(action):
    action = copy.deepcopy(action or {})
    return {
        "farmer": list(action.get("farmer") or ["PASS"]),
        "hands": [list(order or ["PASS"]) for order in (action.get("hands") or [])],
        "market": [list(order) for order in (action.get("market") or [])],
    }


def _seat(obs):
    return 1 if int(_get(obs, "player", 0) or 0) == 1 else 0


def _farm(obs, seat):
    farms = list(_get(obs, "farms", []) or [])
    return farms[seat] if seat < len(farms) else {}


def _align_hands(action, obs):
    action = _copy_action(action)
    expected = len(_get(_farm(obs, _seat(obs)), "hands", []) or [])
    hands = list(action.get("hands") or [])
    if len(hands) < expected:
        hands.extend([["PASS"] for _ in range(expected - len(hands))])
    action["hands"] = [list(order or ["PASS"]) for order in hands[:expected]]
    return action


def _shed_access(size):
    half = size // 2
    return {
        (half - 1, half - 1), (half, half - 1),
        (half - 1, half), (half, half),
    }


def _projected_shed(obs, action):
    farm = _farm(obs, _seat(obs))
    private = _get(obs, "private", {}) or {}
    projected = {
        key: max(0, int(value or 0))
        for key, value in dict(_get(private, "shed", {}) or {}).items()
    }
    inventories = list(_get(private, "inventories", []) or [])
    positions = [_get(farm, "farmer", [0, 0]), *list(_get(farm, "hands", []) or [])]
    unit_actions = [action.get("farmer", ["PASS"]), *list(action.get("hands") or [])]
    tiles = list(_get(farm, "tiles", []) or [])
    access = _shed_access(len(tiles) or 10)
    for index, unit_action in enumerate(unit_actions):
        if index >= len(positions) or index >= len(inventories):
            continue
        position = positions[index]
        if not isinstance(position, (list, tuple)) or len(position) < 2:
            continue
        x, y = int(position[0]), int(position[1])
        if (x, y) not in access or not (0 <= y < len(tiles) and 0 <= x < len(tiles[y])):
            continue
        inventory = {key: max(0, int(value or 0)) for key, value in dict(inventories[index] or {}).items()}
        if unit_action and unit_action[0] == "DROP":
            deposits = inventory.items()
        elif unit_action and unit_action[0] == "PLACE" and len(unit_action) >= 2:
            item = unit_action[1]
            tile = tiles[y][x]
            structure = {"COW": "PASTURE", "SHEEP": "PASTURE", "GOOSE": "COOP"}.get(item)
            if structure and isinstance(tile, dict) and tile.get("kind") == structure and not tile.get("animal"):
                continue
            try:
                requested = int(unit_action[2]) if len(unit_action) >= 3 else 1
            except (TypeError, ValueError):
                continue
            deposits = ((item, min(max(0, requested), inventory.get(item, 0))),)
        else:
            continue
        for item, quantity in deposits:
            room = max(0, 100 - sum(projected.values()))
            amount = min(max(0, int(quantity or 0)), room)
            if amount:
                projected[item] = projected.get(item, 0) + amount
    return projected


def _public_signature(farm):
    keys = (
        "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
        "COW", "SHEEP", "GOOSE", "PASTURE", "COOP", "WEED",
    )
    counts = {key: 0 for key in keys}
    for row in (_get(farm, "tiles", []) or []):
        for tile in row if isinstance(row, list) else [row]:
            if not isinstance(tile, dict):
                continue
            for field in ("crop", "animal", "kind"):
                value = str(tile.get(field, "")).upper()
                if value in counts:
                    counts[value] += 1
                    break
    return (
        len(_get(farm, "hands", []) or []),
        len(_get(farm, "unlocked_quadrants", []) or []),
        tuple(counts[key] for key in sorted(counts)),
    )


def _clone_distance(obs):
    farms = list(_get(obs, "farms", []) or [])
    if len(farms) < 2:
        return 10**9
    left, right = _public_signature(farms[0]), _public_signature(farms[1])
    return (
        abs(left[0] - right[0])
        + 3 * abs(left[1] - right[1])
        + sum(abs(a - b) for a, b in zip(left[2], right[2]))
    )


def _shift_state(obs, step):
    seat = _seat(obs)
    state = _SHIFT_STATE[seat]
    if step == 0 or step < int(state.get("last_step", -1)):
        state = {"last_step": step, "debts": {}}
        _SHIFT_STATE[seat] = state
    state["last_step"] = step
    return state


def _repay_shift(obs, action, step):
    if not _PREEMPT_ENABLED:
        return action
    state = _shift_state(obs, step)
    debts = state.setdefault("debts", {})
    due = {
        item: max(0, int(quantity))
        for item, quantity in dict(debts.pop(step, {}) or {}).items()
    }
    if not due:
        return action
    market = []
    for raw in action.get("market", []) or []:
        order = list(raw)
        if len(order) >= 3 and order[0] == "SELL" and due.get(order[1], 0) > 0:
            item = order[1]
            requested = max(0, int(order[2]))
            reduction = min(requested, due[item])
            requested -= reduction
            due[item] -= reduction
            if requested <= 0:
                continue
            order[2] = requested
        market.append(order)
    action["market"] = market
    return action


def _future_sells(step, horizon):
    future_step = step + horizon
    if future_step >= len(_ACTIONS):
        return {}
    result = {}
    for raw in (_ACTIONS[future_step].get("market") or []):
        if len(raw) >= 3 and raw[0] == "SELL" and raw[1] in _PREMIUM:
            result[raw[1]] = result.get(raw[1], 0) + max(0, int(raw[2]))
    return result


def _preempt_shift(obs, action, step):
    if not _PREEMPT_ENABLED or not (_PREEMPT_START <= step < _PREEMPT_STOP):
        return action
    state = _shift_state(obs, step)
    if _clone_distance(obs) > _PREEMPT_MAX_CLONE_DISTANCE:
        return action
    horizon = _adaptive_horizon(obs, step)
    future = _future_sells(step, horizon)
    if not future:
        return action
    market = list(action.get("market") or [])
    if len(market) >= 10:
        return action
    remaining = _projected_shed(obs, action)
    for raw in market:
        if len(raw) >= 3 and raw[0] == "SELL":
            item = raw[1]
            remaining[item] = max(0, int(remaining.get(item, 0) or 0) - max(0, int(raw[2])))
    prices = _get(_get(obs, "market", {}) or {}, "prices", {}) or {}
    shifted = {}
    for item in _PREMIUM:
        future_quantity = max(0, int(future.get(item, 0) or 0))
        if future_quantity < _PREEMPT_MIN_FUTURE_QUANTITY:
            continue
        base_price = float(_MARKET_PARAMS[item][0])
        if float(_get(prices, item, 0) or 0) < base_price * _PREEMPT_MIN_PRICE_RATIO:
            continue
        target = min(
            max(0, int(remaining.get(item, 0) or 0)),
            future_quantity,
            _PREEMPT_MAX_BATCH,
            max(1, int(round(future_quantity * _PREEMPT_FRACTION))),
        )
        if target <= 0 or len(market) >= 10:
            continue
        market.append(["SELL", item, target])
        remaining[item] = max(0, int(remaining.get(item, 0) or 0) - target)
        shifted[item] = target
    if shifted:
        action["market"] = market[:10]
        due_step = step + horizon
        debts = state.setdefault("debts", {})
        due = debts.setdefault(due_step, {})
        for item, quantity in shifted.items():
            due[item] = due.get(item, 0) + quantity
    return action


def _tile_at(farm, position):
    try:
        x, y = int(position[0]), int(position[1])
        return (_get(farm, "tiles", []) or [])[y][x]
    except (IndexError, TypeError, ValueError):
        return "LOCKED"


def _trace_actor_action(step, actor):
    trace = _ACTIONS[min(max(int(step), 0), len(_ACTIONS) - 1)] or {}
    if actor == "farmer":
        return list(trace.get("farmer") or ["PASS"])
    hands = trace.get("hands", []) or []
    return list(hands[actor] if actor < len(hands) else ["PASS"])


def _weed_repair_action(obs, action, step):
    action = _align_hands(action, obs)
    seat = _seat(obs)
    game = _WEED_STATE[seat]
    if step == 0 or step < game.get("last_step", -1):
        game = {"last_step": step, "active": {}}
        _WEED_STATE[seat] = game
    game["last_step"] = step
    farm = _farm(obs, seat)
    positions = [_get(farm, "farmer"), *list(_get(farm, "hands", []) or [])]
    unit_actions = [action.get("farmer", ["PASS"]), *list(action.get("hands") or [])]
    active = game["active"]

    for actor, transaction in list(active.items()):
        index = 0 if actor == "farmer" else int(actor) + 1
        if index >= len(unit_actions):
            active.pop(actor, None)
            continue
        age = step - transaction["start"]
        if age == 1:
            unit_actions[index] = list(transaction["intended"])
        elif 2 <= age <= 1 + _WEED_REPLAY_STEPS:
            unit_actions[index] = _trace_actor_action(step - 1, actor)
        else:
            active.pop(actor, None)

    for index, (position, intended) in enumerate(zip(positions, unit_actions)):
        actor = "farmer" if index == 0 else index - 1
        if actor in active or not isinstance(intended, list) or not intended:
            continue
        if intended[0] not in ("BUILD_PASTURE", "PLANT"):
            continue
        tile = _tile_at(farm, position)
        if not isinstance(tile, dict) or tile.get("kind") != "WEED":
            continue
        active[actor] = {"start": step, "intended": list(intended)}
        unit_actions[index] = ["DIG"]

    action["farmer"] = unit_actions[0] if unit_actions else ["PASS"]
    action["hands"] = unit_actions[1:]
    return _align_hands(action, obs)


def _shape(name, value):
    value = max(0.0, float(value))
    if name == "linear":
        return value
    if name == "sq":
        return value * value
    if name == "sqrt":
        return math.sqrt(value)
    if name == "log":
        return math.log1p(value)
    if name == "log10":
        return math.log10(1.0 + value)
    raise ValueError(name)


def _market_price(item, inventory):
    base, equilibrium, scale, below_func, below_target, above_func, above_target = _MARKET_PARAMS[item]
    if inventory < equilibrium:
        amplitude = below_target * base / _shape(below_func, scale)
        price = base + amplitude * _shape(below_func, equilibrium - inventory)
    else:
        amplitude = above_target * base / _shape(above_func, scale)
        price = base - amplitude * _shape(above_func, inventory - equilibrium)
    return max(_PRICE_FLOOR, int(round(price)))


def _is_sell(order):
    return (
        isinstance(order, (list, tuple))
        and len(order) >= 3
        and order[0] == "SELL"
        and order[1] in _MARKET_PARAMS
    )


def _impact_score(obs, order):
    if not _is_sell(order):
        return float("-inf")
    item = str(order[1])
    try:
        quantity = max(0, int(order[2]))
    except (TypeError, ValueError):
        return 0.0
    market = _get(obs, "market", {}) or {}
    inventory = _get(market, "inventory", {}) or {}
    prices = _get(market, "prices", {}) or {}
    current_inventory = int(_get(inventory, item, 10000) or 0)
    current_quote = float(_get(prices, item, _market_price(item, current_inventory)) or 0)
    later_quote = float(_market_price(item, current_inventory + quantity))
    return float(quantity) * max(0.0, current_quote - later_quote)


def _demand_per_day(obs, configuration, item):
    town = _get(obs, "town", {}) or {}
    shops = list(_get(town, "unlocked_shops", []) or [])
    turns_per_day = int(_get(configuration, "turnsPerDay", 24) or 24)
    shop_interval = max(1, int(_get(configuration, "townShopSellInterval", 4) or 4))
    demand = 0.0
    for shop in shops:
        products = _SHOP_PRODUCTS.get(shop, ())
        if item in products:
            demand += (turns_per_day / shop_interval) * (2 if len(products) == 1 else 1)
    if item != "FERTILIZER":
        center_interval = max(1, int(_get(configuration, "townCenterSellInterval", 24) or 24))
        demand += turns_per_day / center_interval
    return demand


def _order_score(obs, configuration, order):
    score = _impact_score(obs, order)
    if score <= 0 or not _is_sell(order):
        return score
    item = str(order[1])
    quantity = max(0, int(order[2]))
    market = _get(obs, "market", {}) or {}
    inventory = _get(market, "inventory", {}) or {}
    current_inventory = int(_get(inventory, item, 10000) or 0)
    demand = max(0.25, _demand_per_day(obs, configuration, item))
    excess = max(0.0, current_inventory + quantity - 10000)
    urgency = min(1.0, (excess / demand) / 10.0)
    return score * (1.0 + _DEMAND_ALPHA * urgency)


def _rank_sell_slots(obs, action, configuration):
    action = _copy_action(action)
    market = list(action.get("market") or [])
    rows = [
        (_order_score(obs, configuration, order), -index, list(order))
        for index, order in enumerate(market)
        if _is_sell(order)
    ]
    if len(rows) < 2:
        return action
    rows.sort(reverse=True)
    ranked = iter(row[2] for row in rows)
    action["market"] = [next(ranked) if _is_sell(order) else order for order in market]
    return action


def _terminal_liquidation(obs, action, step):
    if step < 716:
        return action
    action = _copy_action(action)
    shed = _get(_get(obs, "private", {}) or {}, "shed", {}) or {}
    planned = {item: 0 for item in _SELLABLE}
    for order in action.get("market", []):
        if _is_sell(order):
            planned[str(order[1])] += max(0, int(order[2]))
    for item in _LIQUIDATION_ORDER:
        available = max(0, int(_get(shed, item, 0) or 0))
        extra = available if step >= 718 else max(0, available - planned[item])
        if extra and len(action["market"]) < 10:
            action["market"].append(["SELL", item, extra])
    return action


def agent(obs):
    try:
        step = min(max(0, int(_get(obs, "step", 0) or 0)), len(_ACTIONS) - 1)
        _observe_opponent_market(obs, step)
        action = _weed_repair_action(obs, _copy_action(_ACTIONS[step]), step)
        action = _repay_shift(obs, action, step)
        action = _rank_sell_slots(obs, action, None)
        action = _preempt_shift(obs, action, step)
        action = _terminal_liquidation(obs, action, step)
        action = _align_hands(action, obs)
        _record_own_sells(obs, action, step)
        return action
    except Exception:
        farm = _farm(obs, _seat(obs))
        return {
            "farmer": ["PASS"],
            "hands": [["PASS"] for _ in (_get(farm, "hands", []) or [])],
            "market": [],
        }


def _kaggle_submission_entrypoint(obs):
    return agent(obs)
