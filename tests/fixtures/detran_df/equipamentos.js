const equipamentos = [
    {
        "identificacao": "FIS001",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6238",
        "local_instalacao": "VIA L2 SUL SQS 408 SENT. NORTE/SUL - CRUZ 092",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV001.pdf?"
    },
    {
        "identificacao": "FIS002",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6239",
        "local_instalacao": "VIA L2 SUL SGAS 608 SENT. SUL/NORTE - CRUZ 093",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV002.pdf?"
    },
    {
        "identificacao": "FIS003",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6240",
        "local_instalacao": "VIA W3 NORTE SEPN 510 SENT. SUL/NORTE - CRUZ 166",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV003.pdf?"
    },
    {
        "identificacao": "FIS004",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6241",
        "local_instalacao": "VIA W3 NORTE SCLRN 711 SENT. NORTE/SUL - CRUZ 166",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV004.pdf?"
    },
    {
        "identificacao": "FIS005",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6242",
        "local_instalacao": "VIA W4 NORTE SCRN 706 SENT. SUL/NORTE - CRUZ 169",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV005.pdf?"
    },
    {
        "identificacao": "FIS007",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6243",
        "local_instalacao": "W3 SUL SCS SENT SUL/NORTE 054",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV007.pdf?"
    },
    {
        "identificacao": "FIS008",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6244",
        "local_instalacao": "W3 SUL ALT. SHS SENT NORTE/SUL CRUZ 054",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV008.pdf?"
    },
    {
        "identificacao": "FIS009",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6245",
        "local_instalacao": "W3 NORTE ALT. SHN SENT SUL/NORTE CRUZ 158",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV009.pdf?"
    },
    {
        "identificacao": "FIS010",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6246",
        "local_instalacao": "W3 NORTE ALT. SCN SENT NORTE/SUL CRUZ 158",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV010.pdf?"
    },
    {
        "identificacao": "FIS014",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6250",
        "local_instalacao": "AV. COMERCIAL NORTE TAG ALT. QNA 01 SENT. NORTE/SUL - CRUZ 243",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV014.pdf?"
    },
    {
        "identificacao": "FIS016",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6252",
        "local_instalacao": "AV. HELIO PRATES ALT. QNJ AE 02 SENT. CEIL/TAG - CRUZ 274",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV016.pdf?"
    },
    {
        "identificacao": "FIS017",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6253",
        "local_instalacao": "VIA MN1 ALT QNM 18 SENT TAG/CEIL - CRUZ 289",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV017.pdf?"
    },
    {
        "identificacao": "FIS018",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6254",
        "local_instalacao": "VIA MN1 ALT CNM 01 SENT. CEIL/TAG - CRUZ 289",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV018.pdf?"
    },
    {
        "identificacao": "FIS019",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6255",
        "local_instalacao": "VIA MN1 ALT. QNM 02 SENT. TAG/CEIL - CRUZ 293",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV019.pdf?"
    },
    {
        "identificacao": "FIS020",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6256",
        "local_instalacao": "VIA MN1 ALT. QNN 02 SENT. CEIL/TAG - CRUZ 293",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV020.pdf?"
    },
    {
        "identificacao": "FIS021",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6257",
        "local_instalacao": "SHIS QI 05 LAGO SUL/ALT. CHAC 92 SENT Q1 05/QI 07 - CRUZ 135",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV021.pdf?"
    },
    {
        "identificacao": "FIS024",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6258",
        "local_instalacao": "W3 SUL CRS 505 SENT. SUL/NORTE - CRUZ 059",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV024.pdf?"
    },
    {
        "identificacao": "FIS025",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6259",
        "local_instalacao": "W3 SUL SHIGS 704 SENT. NORTE/SUL - CRUZ 059",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV025.pdf?"
    },
    {
        "identificacao": "FIS026",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6260",
        "local_instalacao": "VIA L2 SUL SAS ALT. QD. 06 SENT. NORTE/SUL - CRUZ 082",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV026.pdf?"
    },
    {
        "identificacao": "FIS027",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6261",
        "local_instalacao": "VIA S3 SBS ALT. QD. 04 SENT. SBS/L2 SUL - CRUZ 015",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV027.pdf?"
    },
    {
        "identificacao": "FIS028",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6262",
        "local_instalacao": "VIA L2 NORTE ALT. SQN 406 SENT. NORTE/SUL - CRUZ 203",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV028.pdf?"
    },
    {
        "identificacao": "FIS029",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6263",
        "local_instalacao": "VIA L2 NORTE ALT. SGAN 605 SENT. SUL/NORTE - CRU 204",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV029.pdf?"
    },
    {
        "identificacao": "FIS030",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6264",
        "local_instalacao": "AV. CENTRAL GUARA I ALT. QE 02 SENT. EPTG/GUARA - CRUZ 329",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV030.pdf?"
    },
    {
        "identificacao": "FIS031",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6265",
        "local_instalacao": "AV. CENTRAL GUARA I ALT. QE 07 SENT. GUARA/EPTG - CRUZ 330",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV031.pdf?"
    },
    {
        "identificacao": "FIS032",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6266",
        "local_instalacao": "AV. HELIO PRATES ALT. SDE QD. 01 SETOR M NORTE - CRUZ 353",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV032.pdf?"
    },
    {
        "identificacao": "FIS033",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6267",
        "local_instalacao": "AV. HELIO PRATES ALT. QNL 23 SENT. CEIL/TAG - CRUZ 353",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV033.pdf?"
    },
    {
        "identificacao": "FIS036",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6270",
        "local_instalacao": "VIA S-1 RODOVIARIA RETORNO N1/S1 ALT. SDS - CRUZ 381",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV036.pdf?"
    },
    {
        "identificacao": "FIS037",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6271",
        "local_instalacao": "VIA N1 RODV. ALT. TEATRO NACIONAL SENT L2/W3 NORTE - CRUZ 383",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV037.pdf?"
    },
    {
        "identificacao": "FIS038",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6272",
        "local_instalacao": "VIA W3 NORTE SEPN 506 SENT. SUL/NORTE - CRUZ 162",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV038.pdf?"
    },
    {
        "identificacao": "FIS039",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6273",
        "local_instalacao": "VIA W3 NORTE SCLRN 707 SENT. NORTE/SUL - CRUZ 162",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV039.pdf?"
    },
    {
        "identificacao": "FIS040",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6274",
        "local_instalacao": "VIA W3 NORTE SCRN 502 SENT. SUL/NORTE - CRUZ 160",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV040.pdf?"
    },
    {
        "identificacao": "FIS041",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6275",
        "local_instalacao": "VIA W3 NORTE SCLRN 703 SENT NORTE/SUL - CRUZ 160",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV041.pdf?"
    },
    {
        "identificacao": "FIS042",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6276",
        "local_instalacao": "VIA L2 NORTE ALT. SAUN. QD 05 SENT. NORTE/SUL - CRUZ 198",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV042.pdf?"
    },
    {
        "identificacao": "FIS043",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6277",
        "local_instalacao": "EIXO L NORTE ALT. QD. 01 SNB SENT SUL/NORTE - CRUZ 146",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV043.pdf?"
    },
    {
        "identificacao": "FIS044",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6278",
        "local_instalacao": "VIA W4 SUL SEPS 703/903 SENT SUL/NORTE - CRUZ 079",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV044.pdf?"
    },
    {
        "identificacao": "FIS046",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6279",
        "local_instalacao": "VIA L2 SUL SQS 412 SENT. NORTE/SUL - CRUZ 099",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV046.pdf?"
    },
    {
        "identificacao": "FIS047",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6280",
        "local_instalacao": "VIA L2 SUL SGAS 612 SENT SUL/NORTE - CRUZ 099",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV047.pdf?"
    },
    {
        "identificacao": "FIS048",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6281",
        "local_instalacao": "VIA S3 SMHS 301 SENT. W3/L2 SUL - CRUZ 023",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV048.pdf?"
    },
    {
        "identificacao": "FIS050",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6282",
        "local_instalacao": "VIA W3 SUL CRS 511 SENT. SUL/NORTE - CRUZ -068",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV050.pdf?"
    },
    {
        "identificacao": "FIS051",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6283",
        "local_instalacao": "VIA W3 SUL SRTVS 702 SUL SENT. NORTE/SUL - CRUZ 056",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV051.pdf?"
    },
    {
        "identificacao": "FIS052",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6284",
        "local_instalacao": "VIA L2 SUL SQS 404 SENT. NORTE/SUL - CRUZ 086",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV052.pdf?"
    },
    {
        "identificacao": "FIS053",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6285",
        "local_instalacao": "VIA L2 SUL SGAS 604 SENT SUL/NORTE - CRUZ 087",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV053.pdf?"
    },
    {
        "identificacao": "FIS054",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6286",
        "local_instalacao": "VIA W3 SUL SHIGS 714 SENT. NORTE/SUL - CRUZ 073",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV054.pdf?"
    },
    {
        "identificacao": "FIS055",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6287",
        "local_instalacao": "VIA W5 NORTE SEPN 914 SENT. NORTE/SUL - CRUZ 341",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV055.pdf?"
    },
    {
        "identificacao": "FIS056",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6288",
        "local_instalacao": "VIA W4 NORTE SHIGN 708/709 SENT. SUL/NORTE - CRUZ 349",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV056.pdf?"
    },
    {
        "identificacao": "FIS057",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6289",
        "local_instalacao": "VIA SRPN ALT. CODEPLAN SENT. AUTODROMO/N1 - CRUZ 342",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV057.pdf?"
    },
    {
        "identificacao": "FIS058",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6035",
        "local_instalacao": "VIA N1 CENTRO DE CONVENCES SENT. ESPLAN/RODF - CRUZ 142",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV058.pdf?"
    },
    {
        "identificacao": "FIS059",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6036",
        "local_instalacao": "VIA N1 ALT. TRIBUNAL DE CONTAS SENT. ESPLAN/RODF - CRUZ 153",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV059.pdf?"
    },
    {
        "identificacao": "FIS060",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6290",
        "local_instalacao": "VIA ERNW ALT. SINE SENT NORTE/SUL - CRUZ 148",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV060.pdf?"
    },
    {
        "identificacao": "FIS061",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6291",
        "local_instalacao": "VIA CONTORNO GUARA II ALT. QE 38 - CRUZ 216",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV061.pdf?"
    },
    {
        "identificacao": "FIS062",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6292",
        "local_instalacao": "VIA CONTORNO GUARA II ALT QE 32 SENT. HORARIO - CRUZ 216",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV062.pdf?"
    },
    {
        "identificacao": "FIS064",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6294",
        "local_instalacao": "VIA W3 SUL CRS 513 SENT. SUL/NORTE - CRUZ 072",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV064.pdf?"
    },
    {
        "identificacao": "FIS065",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6295",
        "local_instalacao": "VIA LJ 01 FEIRA PERMANENTE TAG SENT. ELMO SEREJO/HELIO PRATES - CRUZ 320",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV065.pdf?"
    },
    {
        "identificacao": "FIS066",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6296",
        "local_instalacao": "VIA S1 ALT. TJDFT SENT. RODOF/ESPLANADA - CRUZ 006",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV066.pdf?"
    },
    {
        "identificacao": "FIS067",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6297",
        "local_instalacao": "VIA DE LIGACAO W3 NORTE COM EPAA SENT. AUTODROMO/W5 NORTE - CRUZ 174",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV067.pdf?"
    },
    {
        "identificacao": "FIS069",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6298",
        "local_instalacao": "VIA S3 SBS SENT. L2/W3 SUL - CRUZ 019",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV069.pdf?"
    },
    {
        "identificacao": "FIS071",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6299",
        "local_instalacao": "VIA S3 SCS ALT. QD 01 SENT. L2 SUL/W3 SUL - CRUZ 024",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV071.pdf?"
    },
    {
        "identificacao": "FIS072",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6300",
        "local_instalacao": "VIA DE LIGACAO L4 SUL COM SETOR POL. SUL SENT. L4 SUL/SPS - CRUZ 391",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV072.pdf?"
    },
    {
        "identificacao": "FIS073",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6301",
        "local_instalacao": "VIA W3 SUL HIGS 707 SENT. NORTE/SUL - CRUZ 062",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV073.pdf?"
    },
    {
        "identificacao": "FIS076",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6302",
        "local_instalacao": "AV. CENTRAL GUARA I ALT. DA QE 07 SENT. SUL/NORTE - CRUZ 213",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV076.pdf?"
    },
    {
        "identificacao": "FIS077",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6303",
        "local_instalacao": "AV. CENTRAL GUARA I ALT. DA QI 20SENT NORTE/SUL CRUZ 214",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV077.pdf?"
    },
    {
        "identificacao": "FIS078",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6304",
        "local_instalacao": "QNE 05 / QNB 17 TAGUATINGA SENT. AV. COM. NORTE/AV SANDU NORTE - CRUZ 280",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV078.pdf?"
    },
    {
        "identificacao": "FIS079",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6305",
        "local_instalacao": "AV. COMERCIAL SUL QSA 24 SENT. NORTE/SUL TAGUATINGA - CRUZ 240",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV079.pdf?"
    },
    {
        "identificacao": "FIS080",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6306",
        "local_instalacao": "AV. COMERCIAL SUL TAGUATINGA ALT C-8 SENT. NORTE/SUL - CRUZ 242",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV080.pdf?"
    },
    {
        "identificacao": "FIS081",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6307",
        "local_instalacao": "VIA S1 ALT. CRUZ S1/L2 SUL SENT. RODOF/ESPLANADA - CRUZ 002",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV081.pdf?"
    },
    {
        "identificacao": "FIS082",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6308",
        "local_instalacao": "VIA S1 ALT. CRUZ S1/L2 SUL SENT. RODOF/ESPLANADA - CRUZ 002",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV082.pdf?"
    },
    {
        "identificacao": "FIS083",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6309",
        "local_instalacao": "VIA S1 ALT. TJDFT SENT. RODOF/ESPLANADA - CRUZ 006",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV083.pdf?"
    },
    {
        "identificacao": "FIS084",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6310",
        "local_instalacao": "VIA S-1 RODOVIARIA RETORNO N1/S1 ALT. SDS - CRUZ 381",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV084.pdf?"
    },
    {
        "identificacao": "FIS085",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6311",
        "local_instalacao": "VIA N1 RODV. ALT. TEATRO NACIONAL SENT. L2/W3 NORTE - CRUZ 383",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV085.pdf?"
    },
    {
        "identificacao": "FIS086",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6312",
        "local_instalacao": "VIA N1 CENTRO DE CONVECOES SENT. ESPLAN/RODF - CRUZ 142",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV086.pdf?"
    },
    {
        "identificacao": "FIS087",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6313",
        "local_instalacao": "VIA N1 ALT. TRIBUNAL DE CONTAS SENT. ESPLAN/RODOF - CRUZ 153",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV087.pdf?"
    },
    {
        "identificacao": "FIS088",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6314",
        "local_instalacao": "AV. ELMO SEREJO QNM25 SENT. TAG/P SUL - CRUZ 431",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV088.pdf?"
    },
    {
        "identificacao": "FIS090",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6316",
        "local_instalacao": "AV. COMERCIAL NORTE TAG. QND 01 SENT. NORTE/SUL - CRUZ 248",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV090.pdf?"
    },
    {
        "identificacao": "FIS091",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6317",
        "local_instalacao": "AV. SAMDU NORTE QNB 07 TAGUATINGA SENT. SUL/NORTE - CRUZ 282",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV091.pdf?"
    },
    {
        "identificacao": "FIS093",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6318",
        "local_instalacao": "AV. COM. NORTE TAG ONE 17/26 SENT. NORTE/SUL - CRUZ 254",
        "levantamento_estudo": "ARQUIVO INDISPONÍVEL "
    },
    {
        "identificacao": "FIS094",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6319",
        "local_instalacao": "AV. COMERCIAL NORTE TAG CNB 06/07 SENT. NORTE/SUL - CRUZ 246",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV094.pdf?"
    },
    {
        "identificacao": "FIS095",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6320",
        "local_instalacao": "AV. SAMDU NORTE QNE 25/34 TAGUATINGA SENT. SUL/NORTE CRUZ 298",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV095.pdf?"
    },
    {
        "identificacao": "FIS096",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6321",
        "local_instalacao": "VIA W3 SUL ALT. SCRS 508/509 SENT. SUL/NORTE - CRUZ 063",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV096.pdf?"
    },
    {
        "identificacao": "FIS097",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6322",
        "local_instalacao": "VIA W3 SUL ALT. SHIGS 708/709 SENT. NORTE SUL - CRUZ 063",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV097.pdf?"
    },
    {
        "identificacao": "FIS098",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6323",
        "local_instalacao": "AV. DOS PIONEIROS ALT. QD 34/36 GAMA SENT. SANTA MARIA/SETOR OESTE - CRUZ 297",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV098.pdf?"
    },
    {
        "identificacao": "FIS099",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6324",
        "local_instalacao": "AV. DOS PIONEIROS ALT. Q.5 GAMA SENT. SETOR OESTE/SANTA MARIA - CRUZ 297",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV099.pdf?"
    },
    {
        "identificacao": "FIS102",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6325",
        "local_instalacao": "VIA W3 SUL SHIGS 712/713 SENT NORTE/SUL - CRUZ 403",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV102.pdf?"
    },
    {
        "identificacao": "FIS103",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6326",
        "local_instalacao": "VIA N1 ALT. MIN DO EXERCITO SENT. ESPLANADA/RODF - CRUZ 137",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV103.pdf?"
    },
    {
        "identificacao": "FIS104",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6327",
        "local_instalacao": "VIA N1 ALT. MIN DO EXERCITO SENT. ESPLANADA/RODF - CRUZ 137",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV104.pdf?"
    },
    {
        "identificacao": "FIS105",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6328",
        "local_instalacao": "VIA S1 ALT. MIN DA PREVIDENCIA SOCIAL SENT. RODOF/ ESPLANADA - CRUZ 339",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV105.pdf?"
    },
    {
        "identificacao": "FIS106",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6329",
        "local_instalacao": "VIA S1 ALT. MIN DA PREVIDENCIA SOCIAL SENT. RODOF/ ESPLANADA - CRUZ 339",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV106.pdf?"
    },
    {
        "identificacao": "FIS109",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6330",
        "local_instalacao": "VIA W3 NORTE SCRN 508/509 SENT. SUL/NORTE - CRUZ 163",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV109.pdf?"
    },
    {
        "identificacao": "FIS110",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6331",
        "local_instalacao": "VIA W3 NORTE SCRN 514/515 SENT. SUL/NORTE - CRUZ 168",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV110.pdf?"
    },
    {
        "identificacao": "FIS112",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6332",
        "local_instalacao": "AV. ELMO SEREJO QNM 25 SENT. P.SUL/TAGUATINGA - CRUZ 432",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV112.pdf?"
    },
    {
        "identificacao": "FIS113",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6333",
        "local_instalacao": "AV. HELIO PRATES ALT. QND 58 SENT. TAG/ DF001 SEMAF. CRUZ. 256",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV113.pdf?"
    },
    {
        "identificacao": "FIS115",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6334",
        "local_instalacao": "VIA S1 ALT. DA CATEDRAL RAINHA DA PAZ SENT. RODOF/ESPLANADA - CRUZ 394",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV115.pdf?"
    },
    {
        "identificacao": "FIS116",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6335",
        "local_instalacao": "VIA S1 ALT. DA CATEDRAL RAINHA DA PAZ SENT. RODOF/ESPLANADA - CRUZ 394",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV116.pdf?"
    },
    {
        "identificacao": "FIS118",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6336",
        "local_instalacao": "VIA S1 EIXO MONUM. ALT. ACESSO A 1 AV. SUDOESTE SENT. RODF/ESPLANADA - CRUZ 362",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV118.pdf?"
    },
    {
        "identificacao": "FIS119",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6337",
        "local_instalacao": "VIA S1 EIXO MONUM. ALT. ACESSO A 1 AV. SUDOESTE SENT. RODF/ESPLANADA - CRUZ 362",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV119.pdf?"
    },
    {
        "identificacao": "FIS120",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6338",
        "local_instalacao": "1 AVENIDA SUDOESTE ACESSO A VIA S1 EIXO MONUMENTAL - CRUZ 362",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV120.pdf?"
    },
    {
        "identificacao": "FIS123",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6339",
        "local_instalacao": "ALÇA DA RODOVIÁRIA LIGAÇÃO N1/S1 SENTIDO NORTE/SUL SEMAFORO CRUZ\n381",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV123.pdf?"
    },
    {
        "identificacao": "FIS124",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6340",
        "local_instalacao": "VIA MN1 COM N2 ALTURA QNN 18 SENT. CEILANDIA/TAGUATINGA - CRUZ 294",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV124.pdf?"
    },
    {
        "identificacao": "FIS125",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6341",
        "local_instalacao": "VIA MN1 COM N2 ALTURA CNN 1 SENT. TAGUATINGA/CEILANDIA - CRUZ 294",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV125.pdf?"
    },
    {
        "identificacao": "FIS128",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6342",
        "local_instalacao": "VIA M2 ALT. QNM 17 SENTIDO SUL/NORTE - CRUZ 289",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV128.pdf?"
    },
    {
        "identificacao": "FIS129",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6343",
        "local_instalacao": "VIA M2 ALT. CNM 02 SENT. NORTE/SUL - CRUZ 289",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV129.pdf?"
    },
    {
        "identificacao": "FIS130",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6344",
        "local_instalacao": "AV. L2 NORTE SGAN 601 ALT. SERPRO SENT. SUL/NORTE - CRUZ 199",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV130.pdf?"
    },
    {
        "identificacao": "FIS131",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6345",
        "local_instalacao": "VIA LJ 2 ALT. DA QNJ 48 TAGUATINGA SENT. SUL/NORTE - CRUZ 353",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV131.pdf?"
    },
    {
        "identificacao": "FIS132",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6346",
        "local_instalacao": "VIA M 4 ALT. QNM 34 TAGUATINGA SENT. NORTE/SUL - CRUZ 353",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV132.pdf?"
    },
    {
        "identificacao": "FIS133",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6347",
        "local_instalacao": "VIA N1 ALT. SHN QD 04 SENT. ESPLANADA/RODOFERROVIARIA - CRUZ 141",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV133.pdf?"
    },
    {
        "identificacao": "FIS134",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6348",
        "local_instalacao": "VIA N1 ALT. SHN QD 04 SENT ESPLANADA/RODOFERROVIARIA - CRUZ 141",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV134.pdf?"
    },
    {
        "identificacao": "FIS135",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6349",
        "local_instalacao": "AV. COMERCIAL NORTE TAGUATINGA ALT C-9 SENT. NORTE/SUL - CRUZ 227",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV135.pdf?"
    },
    {
        "identificacao": "FIS136",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6350",
        "local_instalacao": "VIA S3 SCS ALT. QD. 06 SENT. W-3/W-4 - CRUZ 055",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV136.pdf?"
    },
    {
        "identificacao": "FIS137",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6351",
        "local_instalacao": "VIA S3 ALT. SRTVS SENT. W-4/W-3 - CRUZ 055",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV137.pdf?"
    },
    {
        "identificacao": "FIS139",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6352",
        "local_instalacao": "AV. SAMDU TAGUATINGA AT. QSB 02 SENT. SUL/NORTE - CRUZ 232",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV139.pdf?"
    },
    {
        "identificacao": "FIS142",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6354",
        "local_instalacao": "AV. CONTORNO CRUZ GUARA I/II PROX. QE 13 SENT. ANTI-HORARIO - CRUZ 215",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV142.pdf?"
    },
    {
        "identificacao": "FIS143",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6355",
        "local_instalacao": "VIA DE ACESSO GUARA I/II ALTURA DO METRO SENT. AV. CONTORNO - CRUZ 215",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV143.pdf?"
    },
    {
        "identificacao": "FIS144",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6356",
        "local_instalacao": "VIA DE LIGACAO N1 COM S1 ALT MEMORIAL DOS POVOS INDIGENAS - CRUZ 005",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV144.pdf?"
    },
    {
        "identificacao": "FIS145",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6357",
        "local_instalacao": "AV. CASTANHEIRAS COM PITANGUEIRAS AGUAS CLARAS SENT. TAGUATINGA - CRUZ 435",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV145.pdf?"
    },
    {
        "identificacao": "FIS146",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6358",
        "local_instalacao": "AV. ARAUVARIAS COM PITANGUEIRAS AGUAS CLARAS SENT. PLANO PILOTO - CRUZ 458",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV146.pdf?"
    },
    {
        "identificacao": "FIS147",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6359",
        "local_instalacao": "AV. DAS JAQUEIRAS ALTURA EQRSW 06/07 SENT.  SUDOESTE/CRUZEIRO  CRUZ. 375",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV147.pdf?"
    },
    {
        "identificacao": "FIS148",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6360",
        "local_instalacao": "AV. DAS JAQUEIRAS ALT. DA Q 10 CRUZEIRO VELHO SENT SUDOESTE / CRUZEIRO CRUZ 376",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV148.pdf?"
    },
    {
        "identificacao": "FIS149",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6361",
        "local_instalacao": "VIA S1 EIXO MONUMENTAL PROX. A TORRE DE TV SENT. ESPLANADA - CRUZ 441",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV149.pdf?"
    },
    {
        "identificacao": "FIS150",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6362",
        "local_instalacao": "VIA S1 EIXO MONUMENTAL PROX. A TORRE DE TV SENT. ESPLANADA - CRUZ 441",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV150.pdf?"
    },
    {
        "identificacao": "FIS151",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6363",
        "local_instalacao": "AV. HELIO PRATES ALT DA QI 15 TAG NORTE SENT. CEIL/DF001 SEMAF. CRUZ. 264",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV151.pdf?"
    },
    {
        "identificacao": "FIS153",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6364",
        "local_instalacao": "VIA MN 1/AV H. PRATES QNN 18/17 CEIL ALT FUND BRADESCO SENT NORTE/SUL - CRUZ 509",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV153.pdf?"
    },
    {
        "identificacao": "FIS154",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6365",
        "local_instalacao": "VIA MN 1/AV H. PRATES QNN 17/18 CEIL ALT FUND BRADESCO SENT NORTE/SUL - CRUZ 509",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV154.pdf?"
    },
    {
        "identificacao": "FIS155",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6366",
        "local_instalacao": "VIA MN 1 AV. H. PRATES QNN 17/18 CEIL FUND BRADESCO SENT CEIL/SETOR P - CRUZ 509",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV155.pdf?"
    },
    {
        "identificacao": "FIS156",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6367",
        "local_instalacao": "VIA MN 1 AV. H PRATES QNN 17/18 CEIL FUND BRADESCO SENT SETOR P/TAG - CRUZ 509",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV156.pdf?"
    },
    {
        "identificacao": "FIS157",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6368",
        "local_instalacao": "GUARA I QE 20 PROX. ESCOLA CLASSE 05 SENT. METRO - CRUZ 378",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV157.pdf?"
    },
    {
        "identificacao": "FIS158",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6369",
        "local_instalacao": "VIA DE LIGACAO S1/N1 ALT. DO MINISTERIO DE INDUSTRIA E COMERCIO - CRUZ 138",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV158.pdf?"
    },
    {
        "identificacao": "FIS159",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6370",
        "local_instalacao": "VIA DE LIGACAO W-3 E W-4 NORTE ALT. QD 707 SENT. AUTODROMO - CRUZ 169",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV159.pdf?"
    },
    {
        "identificacao": "FIS160",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6315",
        "local_instalacao": "AV. ELMO SEREJO CRUZAMENTO COM A QNN 26 CEILÂNDIA  SENT. LESTE/OESTE  -  CRUZ. 512",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV160.pdf?"
    },
    {
        "identificacao": "FIS161",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6248",
        "local_instalacao": "AV. HÉLIO PRATES ALTURA QNJ 07 TAGUATINGA SENT. OESTE/LESTE  - CRUZ 396",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV161.pdf?"
    },
    {
        "identificacao": "FIS162",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6247",
        "local_instalacao": "AV. ARAUCÁRIAS CRUZAMENTO COM PAU BRASIL ÁGUAS CLARAS SENT. OESTE/LESTE  -  CZ 422",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV162.pdf?"
    },
    {
        "identificacao": "FIS163",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6353",
        "local_instalacao": "AV. CASTANHEIRAS CRUZ. COM RUA 36 NORTE ÁGUAS CLARAS SENT. LESTE/OESTE  - CRUZ. 516",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV163.pdf?"
    },
    {
        "identificacao": "FIS164",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6251",
        "local_instalacao": "AV. DAS ARAUCÁRIAS COM AV. SIBIPIRUNA, PRÓX. FEIRA DE ÁGUAS CLARAS - DF CRUZ. 457",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV164.pdf?"
    },
    {
        "identificacao": "FIS165",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6293",
        "local_instalacao": "VIA CENTRAL QI 11 GUARÁ I - DF CRUZ. 377",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV165.pdf?"
    },
    {
        "identificacao": "FIS166",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6268",
        "local_instalacao": "VIA N-3 QNN 34 CRUZAMENTO COM A ELMO SEREJO CEILÂNDIA - DF CRUZ. 512",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV166.pdf?"
    },
    {
        "identificacao": "FIS167",
        "tipo": "AVANÇO DE SINAL VERMELHO",
        "numero_serie": "6269",
        "local_instalacao": "BOULEVARD DE TAGUATINGA C12 BL A TAGUATINGA CRUZ 227",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/avanco/asv/ASV167.pdf?"
    },
    {
        "identificacao": "KR007",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301114, 516301204",
        "local_instalacao": "EIXO W SUL ALT SQS 110 PROXIMO AO BLOCO J SENTIDOÿNORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR007.pdf?"
    },
    {
        "identificacao": "KR008",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301564, 516301146",
        "local_instalacao": "EIXO W SUL ALT SQS 110 PROXIMO AO BLOCO J SENTIDO SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR008.pdf?"
    },
    {
        "identificacao": "KR011",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301028, 516300729",
        "local_instalacao": "AV. ELMO SEREJO ALT QNN26 ( SENT CEIL/TAG)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR011.pdf?"
    },
    {
        "identificacao": "KR012",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301658, 516301480",
        "local_instalacao": "EIXO L SUL SQS 205 PROXIMO A DELEGACIA DA MULHER SENTIDO SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR012.pdf?"
    },
    {
        "identificacao": "KR013",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516300943, 516301145",
        "local_instalacao": "EIXO L SUL SQS 205 PROXIMO A DELEGACIA DA MULHER SENTIDO NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR013.pdf?"
    },
    {
        "identificacao": "KR015",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301483, 516301162, 516300720",
        "local_instalacao": "AV DAS ARAUCARIAS PROX AO CRUZAMENTO COM RUA 35 SENT OESTE/LESTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR015.pdf?"
    },
    {
        "identificacao": "KR016",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301157, 516300800",
        "local_instalacao": "Via M1 QNM 07 CONJUNTO O CEILANDIA SUL PROX CENTRO DE SAUDE N 03 SENT ELMO SEREJO",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR016.pdf?"
    },
    {
        "identificacao": "KR025",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301528, 516301226",
        "local_instalacao": "Via M1 QNM 07 CONJUNTO O CEILANDIA SUL PROX CENTRO DE SAUDE N 03 SENT HELIO PRATES",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR025.pdf?"
    },
    {
        "identificacao": "KR032",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301127",
        "local_instalacao": "AV GOIAS Q2 PLANALTINA (SENT OESTE/LESTE)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR032.pdf?"
    },
    {
        "identificacao": "KR033",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516300810",
        "local_instalacao": "AV GOIAS N100 PLANALTINA (SENT LESTE/OESTE)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR033.pdf?"
    },
    {
        "identificacao": "KR046",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516300934, 516301117",
        "local_instalacao": "EIXO W NORTE EQN Q 102/103 SENT NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR046.pdf?"
    },
    {
        "identificacao": "KR047",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301499, 516301469",
        "local_instalacao": "EIXO W NORTE EQN Q 102/103 SENT SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR047.pdf?"
    },
    {
        "identificacao": "KR048",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301777, 516300799",
        "local_instalacao": "EIXO W NORTE Q 110 (SENT. NORTE/SUL)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR048.pdf?"
    },
    {
        "identificacao": "KR049",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516300798, 516301015",
        "local_instalacao": "EIXO W NORTE Q 110 (SENT. SUL/NORTE)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR049.pdf?"
    },
    {
        "identificacao": "KR052",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516300413",
        "local_instalacao": "VIA DOM ORIONE QI 15 PROX ENTRADA DAS CHAC DE 07 A 12  LAGO SUL  SENT D.ORIONE/AEROPORTO",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR052.pdf?"
    },
    {
        "identificacao": "KR053",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301271",
        "local_instalacao": "VIA DOM ORIONE QI 15 PROX ENTR DAS CHAC DE 07 A 12 LAGO SUL SENT AEROPORTO/DOM ORIONE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR053.pdf?"
    },
    {
        "identificacao": "KR059",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301163, 516301152",
        "local_instalacao": "Via M2 QNM 12 PROX LOTE 38 CEILANDIA NORTE SENTIDO HELIO PRATES",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR059.pdf?"
    },
    {
        "identificacao": "KR060",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516302307, 516301245",
        "local_instalacao": "Via M2 QNM 20 PROX CONJ A CEILANDIA NORTE SENT SETOR O",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR060.pdf?"
    },
    {
        "identificacao": "KR062",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516300417, 516301322",
        "local_instalacao": "2ª AVENIDA SUL QR 302 PROXIMO AO FORUM DE SAMAMBAIA SENTIDO LESTE/OESTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR062.pdf?"
    },
    {
        "identificacao": "KR063",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516300127, 516301326",
        "local_instalacao": "2ª AV SUL QN 514 SENT  OESTE/LESTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR063.pdf?"
    },
    {
        "identificacao": "KR065",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516300407, 516301027",
        "local_instalacao": "AV DOS PIONEIROS Q3 ST SUL GAMA SENT OESTE/LESTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR065.pdf?"
    },
    {
        "identificacao": "KR072",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516302083, 516301454",
        "local_instalacao": "VIA N3 QNN 28 CEILANDIA SENT. SETOR O / ELMO SEREJO",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR072.pdf?"
    },
    {
        "identificacao": "KR073",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301450, 516301453",
        "local_instalacao": "VIA N3 QNN 24 CEIL(SENT E. SEREJO/SET O)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR073.pdf?"
    },
    {
        "identificacao": "KR077",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301551, 516301357",
        "local_instalacao": "VIA N2 QNN 18 PROX CONJ A CEILANDIA SENT HELIO PRATES/ELMO SEREJO",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR077.pdf?"
    },
    {
        "identificacao": "KR082",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301191",
        "local_instalacao": "RUA 5 QD. CENTRAL FRT ED TOPHILL SOBRADINHO (SENT RODOVIÁRIA / HRS)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR082.pdf?"
    },
    {
        "identificacao": "KR083",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301101",
        "local_instalacao": "RUA  5 QD. CENTRAL  FRT ED TOPHILL SOBRADINHO (SENT HRS/RODOVIÁRIA)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR083.pdf?"
    },
    {
        "identificacao": "KR092",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516300208, 516301343",
        "local_instalacao": "2¦ AV SUL QS 314 SAMAMBAIA SENT LESTE/OESTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR092.pdf?"
    },
    {
        "identificacao": "KR093",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301554, 516301016",
        "local_instalacao": "2ª AV SUL QN 506 SAMAM SENT OESTE/LESTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR093.pdf?"
    },
    {
        "identificacao": "KR094",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301025, 516301198",
        "local_instalacao": "VIA HCE FRENTE AOS 01 (SENT OCT/EPIG)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR094.pdf?"
    },
    {
        "identificacao": "KR104",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301476, 516301475",
        "local_instalacao": "AV ALAGADOS CL 107 SANTA MARIA (SENT NORTE/SUL)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR104.pdf?"
    },
    {
        "identificacao": "KR105",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301497, 516300270",
        "local_instalacao": "AV ALAGADOS QR 207 SANTA MARIA (SENT SUL/NORTE)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR105.pdf?"
    },
    {
        "identificacao": "KR108",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301154, 516300432",
        "local_instalacao": "1ª AV NORTE QS 412 SAMAMBAIA (SENT LESTE/OESTE)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR108.pdf?"
    },
    {
        "identificacao": "KR109",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301183, 516301049",
        "local_instalacao": "1ª AV NORTE QN 212 SAMAMBAIA (SENT OESTE/LESTE)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR109.pdf?"
    },
    {
        "identificacao": "KR114",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301132, 516301335",
        "local_instalacao": "1ª AV SUL QS 116 SAMAMBAIA (SENT LESTE/OESTE)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR114.pdf?"
    },
    {
        "identificacao": "KR115",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301071, 516300433",
        "local_instalacao": "1ª AV SUL QN 316 SAMAMBAIA (SENT OESTE/LESTE)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR115.pdf?"
    },
    {
        "identificacao": "KR123",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516300167, 516300904",
        "local_instalacao": "2ª AVENIDA NORTE QN 412 PROX AO CONJ G SENT OESTE/LESTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR123.pdf?"
    },
    {
        "identificacao": "KR130",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301492, 516301346",
        "local_instalacao": "EIXO L NORTE QUADRA 202 SENTIDO NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR130.pdf?"
    },
    {
        "identificacao": "KR131",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301471, 516301473",
        "local_instalacao": "EIXO L NORTE QUADRA 202 SENTIDO SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR131.pdf?"
    },
    {
        "identificacao": "KR132",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516300416, 516301185",
        "local_instalacao": "EIXO L SQN 210 (SENT NORTE/SUL)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR132.pdf?"
    },
    {
        "identificacao": "KR133",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301644, 516300824",
        "local_instalacao": "EIXO L SQN 210 (SENT SUL/NORTE)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR133.pdf?"
    },
    {
        "identificacao": "KR134",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301129, 516301024",
        "local_instalacao": "EIXO L NORTE SQN 206 SENT NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR134.pdf?"
    },
    {
        "identificacao": "KR135",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301488, 516301822",
        "local_instalacao": "EIXO L NORTE SQN 206 SENT SUL/ NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR135.pdf?"
    },
    {
        "identificacao": "KR136",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301188, 516301103",
        "local_instalacao": "EIXO L NORTE Q 214 PROX BLOCO H SENT NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR136.pdf?"
    },
    {
        "identificacao": "KR137",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301110, 516301165",
        "local_instalacao": "EIXO L NORTE Q 214 PROX AO BLOCO H SENTIDO SUL / NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR137.pdf?"
    },
    {
        "identificacao": "KR152",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301350, 516301150, 516301155",
        "local_instalacao": "AV. CONTORNO GUARA II QE 24 PROXIMO A ESTACAO GUARA DO METRO SENT ANTI-HORARIO",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR152.pdf?"
    },
    {
        "identificacao": "KR153",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301140, 516301142, 516300738",
        "local_instalacao": "AV CONT GUARA II QE 30 PROXIMO A IGREJA ASSEMBLEIA DE DEUS SENT HORARIO",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR153.pdf?"
    },
    {
        "identificacao": "KR156",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301586, 516301349, 516301478",
        "local_instalacao": "AV CONTORNO QE 21 GUARA II ( SENT ANTI-HORARIO)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR156.pdf?"
    },
    {
        "identificacao": "KR157",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301656, 516301099, 516301509",
        "local_instalacao": "AV CONTORNO QE 19 GUARA II ( SENT HORARIO)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR157.pdf?"
    },
    {
        "identificacao": "KR158",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516302292, 516301489,516301486",
        "local_instalacao": "VIA RIBEIRÃO  LIGAÇÃO  TAG-SAMAM PROX.  CORR TAG (SENT. NORTE/SUL)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR158.pdf?"
    },
    {
        "identificacao": "KR159",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301192, 516301136, 516300411",
        "local_instalacao": "VIA DE LIG TAG-SAMAM PROX.  CORREGO TAGUATINGA (SENT. SUL/NORTE)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR159.pdf?"
    },
    {
        "identificacao": "KR160",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301263, 516301514",
        "local_instalacao": "AV BOMBEIROS Q. 01 PROX CBM GAMA(SENT SUL/NORTE)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR160.pdf?"
    },
    {
        "identificacao": "KR161",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301991, 516301268",
        "local_instalacao": "AV BOMBEIROS Q. 02 PROX CBM GAMA(SENT NORTE/SUL)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR161.pdf?"
    },
    {
        "identificacao": "KR162",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301102, 516301362",
        "local_instalacao": "AVENIDA DO BOMBEIRO DO GAMA QI 01 PROX AO ESTADIO BEZERRAO SENT SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR162.pdf?"
    },
    {
        "identificacao": "KR163",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301187, 516300333", 
        "local_instalacao": "AVENIDA DO BOMBEIRO DO GAMA PROX AO ESTADIO BEZERRAO SENT NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR163.pdf?"
    },
    {
        "identificacao": "KR170",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301527, 516301445",
        "local_instalacao": "EIXO W SQS 103(SENT NORTE/SUL)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR170.pdf?"
    },
    {
        "identificacao": "KR171",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301363, 516300075",
        "local_instalacao": "EIXO W SQS 103 (SENT SUL/NORTE)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR171.pdf?"
    },
    {
        "identificacao": "KR174",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301078, 516301361",
        "local_instalacao": "EIXO W SUL ALTURA EQS 106/107 PROX AO CINE BRASILIA SENT NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR174.pdf?"
    },
    {
        "identificacao": "KR175",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301169, 516301190",
        "local_instalacao": "EIXO W SUL ALTURA EQS 106/107 PROX AO CINE BRASILIA SENT SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR175.pdf?"
    },
    {
        "identificacao": "KR176",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301318, 516300559",
        "local_instalacao": "EIXO W SUL ALTURA EQS 114/115 PROX AO MCDONALDS SENT NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR176.pdf?"
    },
    {
        "identificacao": "KR177",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301241, 516301111",
        "local_instalacao": "EIXO W SUL ALTURA EQS 114/115 PROX AO MCDONALDS SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR177.pdf?"
    },
    {
        "identificacao": "KR178",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301295, 516300373",
        "local_instalacao": "EIXO W SQN 106 (SENT NORTE/SUL) ",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR178.pdf?"
    },
    {
        "identificacao": "KR179",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301053, 516301619",
        "local_instalacao": "EIXO W NORTE SQN 106 (SENT. SUL/NORTE)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR179.pdf?"
    },
    {
        "identificacao": "KR180",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301044, 516301364, 516301277",
        "local_instalacao": "W4 NORTE Q 711/911 PROXIMO A IGREJA DE JESUS CRISTO SENT SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR180.pdf?"
    },
    {
        "identificacao": "KR182",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301141, 516301324, 516301279",
        "local_instalacao": "W4 NORTE ALTURA DA HCGN 715 SENT SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR182.pdf?"
    },
    {
        "identificacao": "KR183",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516300418, 516300434, 516301643",
        "local_instalacao": "W5 SGAN 904 (SENT NORTE/SUL)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR183.pdf?"
    },
    {
        "identificacao": "KR184",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301072, 516301252, 516301468",
        "local_instalacao": "SETOR POLICIAL SUL FRENTE QCG PM SENT. CRUZEIRO",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR184.pdf?"
    },
    {
        "identificacao": "KR195",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516300794, 516301203, 516301200, 516301260, 516301235, 516301243",
        "local_instalacao": "VIA N1 E. MONUM ALT SMU (SENT SHOPPING POPULAR)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR195.pdf?"
    },
    {
        "identificacao": "KR203",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301585, 516301240, 516301663, 516300718, 516301246, 516301229",
        "local_instalacao": "VIA S1 E. MONUM CRUZ VELHO (SENT CONGRESSO)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR203.pdf?"
    },
    {
        "identificacao": "KR205",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301247, 516301330",
        "local_instalacao": "EIXO L SQS 209 (SENT NORTE/SUL)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR205.pdf?"
    },
    {
        "identificacao": "KR206",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301238, 516301251",
        "local_instalacao": "EIXO L SQS 209 (SENT SUL/NORTE)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR206.pdf?"
    },
    {
        "identificacao": "KR212",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301159, 516301495",
        "local_instalacao": "EPCB (AV. DAS JAQUEIRAS) PROX Q 1311 SENT.  NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR212.pdf?"
    },
    {
        "identificacao": "KR213",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301756, 516301195",
        "local_instalacao": "EPCB (AV. DAS JAQUEIRAS QRSW 1/2 PROX A IGREJA SAO PIO DE PIETRELCINA SENT SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR213.pdf?"
    },
    {
        "identificacao": "KR216",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516302569, 516301325",
        "local_instalacao": "VIA M2 CEIL QNM 22 CONJ A FRENTE LT 13 SENT SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR216.pdf?"
    },
    {
        "identificacao": "KR218",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301100, 516301482",
        "local_instalacao": "VIA MN2 CEIL QNN 07 CONJ A FRENTE LT 14 SENT. NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR218.pdf?"
    },
    {
        "identificacao": "KR219",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516300786, 516301223",
        "local_instalacao": "VIA MN2 CEIL QNM 08 CONJ A FRENTE LT 21 SENT. SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR219.pdf?"
    },
    {
        "identificacao": "KR221",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516302586, 516300398",
        "local_instalacao": "VIA LW1 BRAZLANDIA PROX CH 1A SUL SETOR SUL SENT DF180/CENTRO",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR221.pdf?"
    },
    {
        "identificacao": "KR224",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301239, 516300739, 516301097",
        "local_instalacao": "VIA JK ENTRADA DA PONTE JK (SENT PLANO PILOTO/LAGO SUL)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR224.pdf?"
    },
    {
        "identificacao": "KR225",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516300184, 516301406, 516301221",
        "local_instalacao": "VIA JK ENTRADA DA PONTE JK (SENT LAGO SUL/PLANO PILOTO)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR225.pdf?"
    },
    {
        "identificacao": "KR232",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516302144",
        "local_instalacao": "SHIS QI 03 FRENTE A VILA NPV LAGO SULSENTIDO DF-025(EPDB)/QI 15",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR232.pdf?"
    },
    {
        "identificacao": "KR233",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301467",
        "local_instalacao": "SHIS QI 03 FRENTE A VILA NPV LAGO SULSENTIDO QI 15/DF-025(EPDB)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR233.pdf?"
    },
    {
        "identificacao": "KR234",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301151, 516301470, 516301208",
        "local_instalacao": "L2 NORTE ALT SQN 411 SENTIDO NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR234.pdf?"
    },
    {
        "identificacao": "KR235",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301479, 516301472, 516301033",
        "local_instalacao": "L2 NORTE ALT SGAN 611 SENTIDO SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR235.pdf?"
    },
    {
        "identificacao": "KR236",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516300825, 516300847, 516300222",
        "local_instalacao": "VIA TERMINAL NORTE 320m ANTES DO 2:CBM SENT DF003(EPIA)/W3 NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR236.pdf?"
    },
    {
        "identificacao": "KR240",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301642, 516301327, 516300435",
        "local_instalacao": "W4 NORTE HCGN 704 PROX BLOCO I SENT SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR240.pdf?"
    },
    {
        "identificacao": "KR247",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301211, 516301232, 516301122",
        "local_instalacao": "VIA N1 EIXO MONUM PROX PAVILHAO DAS METAS (MEC) SENT CONGRESSO/PAL DA ALVORADA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR247.pdf?"
    },
    {
        "identificacao": "KR248",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301244, 516300436, 516301166",
        "local_instalacao": "VIA N1 EIXO MONUM A 130 DA ENTR DO 1º BAT DE INC(CBM) SENT PAL DA ALVORADA/CONG",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR248.pdf?"
    },
    {
        "identificacao": "KR249",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516300920, 516301336",
        "local_instalacao": "VIA DE LIG L2-PONTE COSTA E SILVA A 70m DO VIAD. DA L3 SENT P. PILOTO/LAGO SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR249.pdf?"
    },
    {
        "identificacao": "KR258",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516300585, 516301474",
        "local_instalacao": "VIA M1 CEIL QNM 04 CONJ O FRENTE LT 14 SENT NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR258.pdf?"
    },
    {
        "identificacao": "KR259",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301339, 516300775",
        "local_instalacao": "VIA M1 CEILANDIA ALT DA QNM 12  SENT SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR259.pdf?"
    },
    {
        "identificacao": "KR260",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301148, 516301135",
        "local_instalacao": "EIXO L SUL SQS 202 PROX BL H SENT NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR260.pdf?"
    },
    {
        "identificacao": "KR261",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301061, 516300726",
        "local_instalacao": "EIXO L SUL SQS 202 PROX BL L SENTIDO SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR261.pdf?"
    },
    {
        "identificacao": "KR262",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516300813, 516301261",
        "local_instalacao": "VIA M3 CEIL QNM 29 PROX APAED SENT ELMO SEREJO /HELIO PRATES",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR262.pdf?"
    },
    {
        "identificacao": "KR263",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301498, 516301270",
        "local_instalacao": "VIA M3 M NORTE CEIL QNM 40 PROX CONJ F2 SENT HELIO PRATES/SETOR O",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR263.pdf?"
    },
    {
        "identificacao": "KR264",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301276, 516301334",
        "local_instalacao": "AV SAO SEBASTIAO ALT Q 11 CONJ A SENT LESTE/OESTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR264.pdf?"
    },
    {
        "identificacao": "KR265",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301143, 516301597",
        "local_instalacao": "AV SAO SEBASTIAO ALT Q 11 CONJ A SENT OESTE/LESTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR265.pdf?"
    },
    {
        "identificacao": "KR266",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301115, 516301236, 516301121",
        "local_instalacao": "AV L3 NORTE Q 608 FRENTE POSTO BR DA UNB SENT NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR266.pdf?"
    },
    {
        "identificacao": "KR267",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516300880, 516300145, 516300041",
        "local_instalacao": "AV L3 NORTE PROX A FINATEC SENT SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR267.pdf?"
    },
    {
        "identificacao": "KR268",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301278, 516301345",
        "local_instalacao": "AV LESTE SAMAMBAIA ALT VIAD METRO SENT NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR268.pdf?"
    },
    {
        "identificacao": "KR269",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301494, 516302039",
        "local_instalacao": "AV LESTE SAMAMBAIA ALT VIAD METRO SENT SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR269.pdf?"
    },
    {
        "identificacao": "KR270",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301556, 516301199",
        "local_instalacao": "AV RECANTO DAS EMAS Q 104 AO LADO CASTELO FORTE (SENT. LESTE/OESTE)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR270.pdf?"
    },
    {
        "identificacao": "KR271",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301126, 516301337",
        "local_instalacao": "AV RECANTO DAS EMAS Q 206 AO LADO CASTELO FORTE (SENT OESTE/LESTE)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR271.pdf?"
    },
    {
        "identificacao": "KR272",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516300661, 516301578, 516300960",
        "local_instalacao": "VIA JK SAIDA DA PONTE SENTIDO LAGO SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR272.pdf?"
    },
    {
        "identificacao": "KR273",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301562, 516301340, 516300930",
        "local_instalacao": "VIA JK SAIDA DA PONTE JK (SENT. PLANO PILOTO)",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR273.pdf?"
    },
    {
        "identificacao": "KR275",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301512, 516301124",
        "local_instalacao": "1ª AVENIDA SUDOESTE QMSW 05 LT. 02 PROX. BL. C SENT. NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR275.pdf?"
    },
    {
        "identificacao": "KR277",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301125",
        "local_instalacao": "AV CONDOMINIO JARDIM AMERICA ALT CHACARA 02 - SOBRADINHO SENT DF150",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR277.pdf?"
    },
    {
        "identificacao": "KR278",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516302589",
        "local_instalacao": "AV CONDOMINIO JARDIM AMERICA ALT CHACARA 02 – SOBRADINHO SENT BR 020",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR278.pdf?"
    },
    {
        "identificacao": "KR279",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301207, 516300773",
        "local_instalacao": "VIA M3 SUL QNM 21 PROXIMO AO CONJ P SENTIDO ELMO SEREJO",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR279.pdf?"
    },
    {
        "identificacao": "KR280",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301323, 516301312",
        "local_instalacao": "VIA M3 QNM 19 PROX CONJ O CEILANDIA SUL SENTIDO ELMO SEREJO",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR280.pdf?"
    },
    {
        "identificacao": "KR283",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301064, 516301098",
        "local_instalacao": "EIXO L SUL ALTURA SQS 212 PROXIMO A IGREJA UNIVERSAL SENT NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR283.pdf?"
    },
    {
        "identificacao": "KR284",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301171, 516300963",
        "local_instalacao": "EIXO L SUL ALTURA SQS 212 PROXIMO A IGREJA UNIVERSAL SENT SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR284.pdf?"
    },
    {
        "identificacao": "KR285",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301451",
        "local_instalacao": "SHIS QI 01 PROX AO CONJUNTO 01 SENT EPDB/VI COMAR",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR285.pdf?"
    },
    {
        "identificacao": "KR289",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301317, 516300802",
        "local_instalacao": "VIA M3 QNM 27 PROX COORD REGIONAL DE ENSINO DE CEILANDIA SENT SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR289.pdf?"
    },
    {
        "identificacao": "KR296",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516300756, 516301560",
        "local_instalacao": "VIA M3 QNM 30 MOD F CEILANDIA NORTE PROX CENTRO ASSIST MARIA CARMEM SENT SUL/ NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR296.pdf?"
    },
    {
        "identificacao": "KR297",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301552, 516300583",
        "local_instalacao": "VIA M3 NORTE QNM 28 MODULO A PROXIMO A ASSEMBLEIA DE DEUS SENT. SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR297.pdf?"
    },
    {
        "identificacao": "KR298",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301201, 516301259",
        "local_instalacao": "VIA M3 SUL QNM 23 PROX AO CONJ P SENT NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR298.pdf?"
    },
    {
        "identificacao": "KR301",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516300757, 516301045",
        "local_instalacao": "VIA M3 NORTE QNM 20 PROX AO CONJUNTO O SENTIDO HELIO PRATES",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR301.pdf?"
    },
    {
        "identificacao": "KR304",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301112, 516301216",
        "local_instalacao": "VIA M3 SUL QNM 25 PROXIMO AO CLUBE DO FLAMENGO SENTIDO HELIO PRATES",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR304.pdf?"
    },
    {
        "identificacao": "KR305",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516300111, 516301548, 516301167",
        "local_instalacao": "AVENIDA DO EXERCITO PROXIMO AO QG SENTIDO NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR305.pdf?"
    },
    {
        "identificacao": "KR306",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516300261",
        "local_instalacao": "SHIS QI 03 PROX AO CONJUNTO 01 SENT VI COMAR/EPDB",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR306.pdf?"
    },
    {
        "identificacao": "KR310",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516300643, 516300581, 516301621",
        "local_instalacao": "AVENIDA DOS EXERCITO PROXIMO AO QG SENTIDO SUL/ NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR310.pdf?"
    },
    {
        "identificacao": "KR311",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301128, 516301213",
        "local_instalacao": "AV CENTRAL NORTE Q 01 AE SETOR NORTE GAMA PROX AO FORUM SENT SESI",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR311.pdf?"
    },
    {
        "identificacao": "KR312",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301526, 516301186",
        "local_instalacao": "AV CENTRAL NORTE AREA ESPECIAL 1/8 SETOR CENTRAL GAMA PROX SESI SENT FORUM",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR312.pdf?"
    },
    {
        "identificacao": "KR319",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301320, 516301144, 516301139",
        "local_instalacao": "AV. CASTANHEIRAS RUA 18 NORTE PRàX. AO POSTO DE GASOLINA SENT. TAGUATINGA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR319.pdf?"
    },
    {
        "identificacao": "KR321",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516302032",
        "local_instalacao": "AV EUCALIPTOS ALTURA QD 01 PROX A VILA OLIMPICA - SAO SEBASTIAO SENT NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR321.pdf?"
    },
    {
        "identificacao": "KR322",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301242",
        "local_instalacao": "AV EUCALIPTOS ALT QD 01 PROX. A VILA OLIMPICA - SAO SEBASTIAO SENT SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR322.pdf?"
    },
    {
        "identificacao": "KR323",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301253, 516301134",
        "local_instalacao": "AVENIDA CENTRAL PROX A ESCOLA CLASSE 02 CIDADE ESTRUTURAL SENTIDO LESTE/OESTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR323.pdf?"
    },
    {
        "identificacao": "KR324",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301040",
        "local_instalacao": "AV SANDU SUL QSD 45 SENTIDO TAGUATINGA NORTE - TAGUATINGA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR324.pdf?"
    },
    {
        "identificacao": "KR325",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516300803",
        "local_instalacao": "AV SANDU SUL QSD 26 PROX CASA 05 SENTIDO BR-060 -  TAGUATINGA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR325.pdf?"
    },
    {
        "identificacao": "KR343",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301119, 516301249, 516301046",
        "local_instalacao": "AVENIDA W3 SUL ALTURA DA SHIGS 711 SENTNORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR343.pdf?"
    },
    {
        "identificacao": "KR344",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301254, 516301490, 516301503",
        "local_instalacao": "AVENIDA W3 SUL ALTURA DA SHIGS 713 SENTNORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR344.pdf?"
    },
    {
        "identificacao": "KR347",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301264, 516301255, 516301394",
        "local_instalacao": "AV. W-3 NORTE ALT DA SCLRN 716 SENT SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR347.pdf?"
    },
    {
        "identificacao": "KR363",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301449, 516301332",
        "local_instalacao": "AV. W-7 NORTE SQNW 102 NOROESTE SENT. SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR363.pdf?"
    },
    {
        "identificacao": "KR364",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301618, 516301222",
        "local_instalacao": "AV. W-7 NORTE SQNW 102 NOROESTE SENT. NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR364.pdf?"
    },
    {
        "identificacao": "KR365",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301465, 516301193",
        "local_instalacao": "AV. W-7 NORTE SQNW 106 NOROESTE SENT. SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR365.pdf?"
    },
    {
        "identificacao": "KR366",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301292, 516301160",
        "local_instalacao": "AV. W-7 NORTE SQNW 106 NOROESTE SENT. NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR366.pdf?"
    },
    {
        "identificacao": "KR368",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301485, 516301537",
        "local_instalacao": "AV. MANGUEIRAL A 120 METROS DA ENTRADA DA VIA SENT. SAO SEBASTIAO",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR368.pdf?"
    },
    {
        "identificacao": "KR370",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301205, 516301484, 516301553",
        "local_instalacao": "SETOR POLICIAL SUL EM FRENTE ABIN SENT. CRUZEIRO",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR370.pdf?"
    },
    {
        "identificacao": "KR371",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301257, 516301138, 516301202",
        "local_instalacao": "SETOR POLICIAL SUL FRENTE ABIN SENT. ASA SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR371.pdf?"
    },
    {
        "identificacao": "KR372",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516300584, 516301796",
        "local_instalacao": "SETOR O NORTE QNO 4 CONJUNTO L CEILANDIA SENTIDO NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR372.pdf?"
    },
    {
        "identificacao": "KR373",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516302309, 516301158",
        "local_instalacao": "SETOR O NORTE QNO 4 CONJUNTO M CEILANDIA SENTIDO SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR373.pdf?"
    },
    {
        "identificacao": "KR374",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301161, 516300762, 516301316",
        "local_instalacao": "VIA LJ-1 QNL 07 BL. B TAGUATINGA SENTIDO NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR374.pdf?"
    },
    {
        "identificacao": "KR375",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516300008, 516301130",
        "local_instalacao": "VIA LJ-1 QNL 08 BL. B TAGUATINGA SENTIDO SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR375.pdf?"
    },
    {
        "identificacao": "KR376",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516302568, 516301227, 516302094",
        "local_instalacao": "VIA TERMINAL NORTE A 200m DA 2ª DP ASA NORTE PLANO PILOTO SENT. W-3 NORTE/DF-003",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR376.pdf?"
    },
    {
        "identificacao": "KR377",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516300774, 516301881, 516300314",
        "local_instalacao": "AV. W-3 NORTE ALT. SEPN Q. 516 LT. 10 ASA NORTE PLANO PILOTO SENT SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR377.pdf?"
    },
    {
        "identificacao": "KR378",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301233, 516301750, 516301177",
        "local_instalacao": "AV. W-3 SUL ALT. SHLS Q. 716 LT. 2 ASA SUL PLANO PILOTO SENT. NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR378.pdf?"
    },
    {
        "identificacao": "KR379",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516300728, 516301156",
        "local_instalacao": "VIA NM3 ST. O QNN33 CEILÂNDIA - DF SENT. OESTE/LESTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR379.pdf?"
    },
    {
        "identificacao": "KR380",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301518, 516300652",
        "local_instalacao": "VIA NM3 ST. O QNO 9 CEILÂNDIA - DF SENT. LESTE/OESTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR380.pdf?"
    },
    {
        "identificacao": "KR381",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516300397, 516300520, 516301258",
        "local_instalacao": "SQSW 105 PROX. COND. EDIFICIO VIA ROMA SUDOESTE - DF",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR381.pdf?"
    },
    {
        "identificacao": "KR382",
        "tipo": "DETRAN - RADAR",
        "numero_serie": "516301342, 516301978",
        "local_instalacao": "AVENIDA DO EXÉRCITO PROX. A QUADRA RESIDENCIAL DE GENERAIS - DF",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/radar/dtr/DTR382.pdf?"
    },
    {
        "identificacao": "RE001",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13195/R13188",
        "local_instalacao": "VIA L-3 NORTE ALTURA DA FACULDADE DE EDUCAÇÃO/UNB SENT. SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT001.pdf?"
    },
    {
        "identificacao": "RE002",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R12603/R12606",
        "local_instalacao": "VIA L-3 NORTE ALTURA DA SGAN 606 PROX. CASA THOMAS JEFERSON SENT. NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT002.pdf?"
    },
    {
        "identificacao": "RE003",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13160",
        "local_instalacao": "VIA M1 QNM 14 AREA ESPECIAL PROX CENTRO ENSINO 02 CEILÂNDIA SENT. BR-070",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT003.pdf?"
    },
    {
        "identificacao": "RE004",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13161",
        "local_instalacao": "VIA M1 QNM 06 CONJ P CEILÂNDIA SENT. HELIO PRATES",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT004.pdf?"
    },
    {
        "identificacao": "RE005",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13172",
        "local_instalacao": "VIA N-3 QNO 10 LOTE A PROX AO CAIC  CEILÂNDIA SENT. HELIO PRATES",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT005.pdf?"
    },
    {
        "identificacao": "RE006",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R12989",
        "local_instalacao": "VIA N-3 QNO 11 CONJ B SENT.  BR-070 CEILÂNDIA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT006.pdf?"
    },
    {
        "identificacao": "RE007",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R12990",
        "local_instalacao": "VIA N3 QNN 31 AREA ESPECIAL PROX COLEGIO SALESIANO CEILÂNDIA SENT. HELIO PRATES",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT007.pdf?"
    },
    {
        "identificacao": "RE008",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R12991",
        "local_instalacao": "VIA N-3 QNN 23 CONJ P SENT. BR-070 CEILANDIA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT008.pdf?"
    },
    {
        "identificacao": "RE009",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R12992",
        "local_instalacao": "VIA N-3 QNN 27 LOTE C PROX SESC SENT. HELIO PRATES CEILANDIA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT009.pdf?"
    },
    {
        "identificacao": "RE010",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R12993",
        "local_instalacao": "VIA N-3 QNN 19 CONJ O CEILÂNDIA SENT. BR-070",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT010.pdf?"
    },
    {
        "identificacao": "RE011",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R12994",
        "local_instalacao": "VIA N3 QNN 28 PROX AO SUPERCEI SENT. ELMO SEREJO CEILANDIA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT011.pdf?"
    },
    {
        "identificacao": "RE012",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R12995",
        "local_instalacao": "VIA N3 QNN 20 CONJ \"O\" SENT. HELIO PRATES CEILANDIA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT012.pdf?"
    },
    {
        "identificacao": "RE013",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13162/R13191",
        "local_instalacao": "VIA LJ2 QNL11 BLOCO \"G\" TAGUATINGA SENT. ELMO SEREJO",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT013.pdf?"
    },
    {
        "identificacao": "RE014",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13163",
        "local_instalacao": "VIA LJ-2 QNL 01 BLOCO J SENT. HELIO PRATES/TAGUATINGA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT014.pdf?"
    },
    {
        "identificacao": "RE015",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R12996",
        "local_instalacao": "VIA N2 QNN 14 AREA ESPECIAL EM FRENTE \"C.E.P.\" CEILÂNDIA SENT. HELIO PRATES",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT015.pdf?"
    },
    {
        "identificacao": "RE016",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R12997",
        "local_instalacao": "VIA N2 QNN 20 CONJ \"B\" CEILÂNDIA SENT. ELMO SEREJO",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT016.pdf?"
    },
    {
        "identificacao": "RE020",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13164",
        "local_instalacao": "VIA MN2 QNN 08 CONJUNTO B SENT. ELMO SEREJO CEILÂNDIA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT020.pdf?"
    },
    {
        "identificacao": "RE021",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13165",
        "local_instalacao": "VIA MN2 QNM 08 CONJ. B LT 46 CEILANDIA SENT. SUL/NORTE ",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT021.pdf?"
    },
    {
        "identificacao": "RE022",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13166",
        "local_instalacao": "VIA MN-2 QNN 09 CONJ. A LT. 46 CEILANDIA SENT. NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT022.pdf?"
    },
    {
        "identificacao": "RE023",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13167",
        "local_instalacao": "VIA MN-2 QNM 04 CONJ \"B\" SENT. BR-070 CEILANDIA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT023.pdf?"
    },
    {
        "identificacao": "RE024",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13168",
        "local_instalacao": "VIA MN2 QNM 05 CONJ \"A\" SENT. HELIO PRATES PROX. SUPERM. ESPIRITO SANTO CEILANDIA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT024.pdf?"
    },
    {
        "identificacao": "RE025",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13295",
        "local_instalacao": "VIA SC 05/AV. DOS PIONEIROS Q 01 CONJ. G LT. 23 GAMA SENT. OESTE/LESTE ",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT025.pdf?"
    },
    {
        "identificacao": "RE026",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13296",
        "local_instalacao": "VIA SC5/AV. DOS PIONEIROS Q 45 GAMA SENT. LESTE/OESTE ",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT026.pdf?"
    },
    {
        "identificacao": "RE029",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13169",
        "local_instalacao": "2ª AV. NORTE QN 410 CONJ J SENTIDO OESTE/LESTE - SAMAMBAIA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT029.pdf?"
    },
    {
        "identificacao": "RE030",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13313",
        "local_instalacao": "2ª AVENIDA NORTE QS 610 SENT. LESTE/OESTE - SAMAMBAIA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT030.pdf?"
    },
    {
        "identificacao": "RE031",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13171",
        "local_instalacao": "1ª AV. NORTE ALT. QS 410/408 SENTIDO LESTE/OESTE -SAMAMBAIA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT031.pdf?"
    },
    {
        "identificacao": "RE032",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13307",
        "local_instalacao": "1ª AV. NORTE QN 208 CONJ D SENTIDO OESTE/LESTE - SAMAMBAIA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT032.pdf?"
    },
    {
        "identificacao": "RE033",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13297",
        "local_instalacao": "1º AVENIDA SUL QS110 CONJ 08 SENT. LESTE/OESTE SAMAMBAIA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT033.pdf?"
    },
    {
        "identificacao": "RE034",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13298",
        "local_instalacao": "1ª AVENIDA SUL QN 308 CONJ 04 SENT. OESTE/LESTE SAMAMBAIA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT034.pdf?"
    },
    {
        "identificacao": "RE035",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13299",
        "local_instalacao": "1ª AVENIDA SUL QS120/122 SAMAMBAIA SENT. LESTE/OESTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT035.pdf?"
    },
    {
        "identificacao": "RE036",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13001",
        "local_instalacao": "1ª AVENIDA SUL QN 320 CONJ 01 SAMAMBAIA SENT. OESTE/LESTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT036.pdf?"
    },
    {
        "identificacao": "RE039",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13300",
        "local_instalacao": "AV. RECANTO DAS EMAS Q 300 SENT. EPCT - RECANTO  DAS EMAS",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT039.pdf?"
    },
    {
        "identificacao": "RE040",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13301",
        "local_instalacao": "AV. RECANTO DAS EMAS Q 106 SENT. LESTE/OESTE - RECANTO DAS EMAS",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT040.pdf?"
    },
    {
        "identificacao": "RE041",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13302",
        "local_instalacao": "AV. RECANTO DAS EMAS Q 101 LOTE 17 SENT. LESTE/OESTE - RECANTO DAS EMAS",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT041.pdf?"
    },
    {
        "identificacao": "RE042",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13303",
        "local_instalacao": "AV. RECANTO DAS EMAS ALT. Q 201 LOTE 17 SENTIDO OESTE/LESTE - RECANTO DAS EMAS",
        "levantamento_estudo":"https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT042.pdf?"
    },
    {
        "identificacao": "RE043",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13328",
        "local_instalacao": "VIA M2 QNM 24 CONJ. A SENT. BR-070 CEILANDIA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT043.pdf?"
    },
    {
        "identificacao": "RE044",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13174",
        "local_instalacao": "VIA M-2 QNM 16 AE F EM FRENTE AO CENTRO 05 SENT HELIO PRATES CEILANDIA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT044.pdf?"
    },
    {
        "identificacao": "RE045",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13175",
        "local_instalacao": "VIA M2 QNM 21 CONJ \"A\" CEILANDIA SENTIDO HELIO PRATES",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT045.pdf?"
    },
    {
        "identificacao": "RE046",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R12998",
        "local_instalacao": "VIA M2 QNM 13  PROX. CENTRO DE ENSINO 03 SENT. ELMO SEREJO CEILANDIA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT046.pdf?"
    },
    {
        "identificacao": "RE047",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13304",
        "local_instalacao": "VIA AO1 AOS 4/5 ALT BLOCO C SENT. ANTI HORARIO - OCTOGONAL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT047.pdf?"
    },
    {
        "identificacao": "RE048",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13305",
        "local_instalacao": "VIA AO1 AOS 4/5 SENT. HORARIO - OCTOGONAL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT048.pdf?"
    },
    {
        "identificacao": "RE049",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13664/R13644",
        "local_instalacao": "AV. CONTORNO GUARA II QE 38 AREA ESPECIAL SENT. ANTIHORARIO",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT049.pdf?"
    },
    {
        "identificacao": "RE050",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13665/R13645",
        "local_instalacao": "VIA CONTORNO DO GUARA II QE 34 CONJ \"A\" SENT. HORÁRIO",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT050.pdf?"
    },
    {
        "identificacao": "RE053",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13306/R13330",
        "local_instalacao": "VIA W4 NORTE SHCGN 713/714 SENT. SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT053.pdf?"
    },
    {
        "identificacao": "RE054",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R12604/R12607",
        "local_instalacao": "RUA 3 QD. 12 AE PROX.  AO CENTRO EDUCACIONAL 02 SOBRADINHO",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT054.pdf?"
    },
    {
        "identificacao": "RE055",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R12608/R12605",
        "local_instalacao": "RUA 3 QD. 13 ALT. CONJ. B PROX. SUPERMERCADO SAMPAIO SOBRADINHO",
        "levantamento_estudo":"https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT055.pdf?"
    },
    {
        "identificacao": "RE056",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R12611",
        "local_instalacao": "QD. 08 CL 08 LOTE 03 PROX. CENTRO DE ENSINO 05 SENT. LESTE/OESTE SOBRADINHO",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT056.pdf?"
    },
    {
        "identificacao": "RE057",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R12612",
        "local_instalacao": "QD 10 CONJ B PROX. AO CENTRO DE ENSINO 05 SENT. OESTE/LESTE SOBRADINHO I",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT057.pdf?"
    },
    {
        "identificacao": "RE058",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R12988",
        "local_instalacao": "AV ERASMO DE CASTRO EM FRENTE AO LAR FABIANO DE CRISTO SENT. ARAPOANGA PLANALTINA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT058.pdf?"
    },
    {
        "identificacao": "RE064",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13308",
        "local_instalacao": "AV INDEPENDENCIA SR JARDIM RORIZ QD 01 CONJ. 1H PLANALTINA SENT. SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT064.pdf?"
    },
    {
        "identificacao": "RE066",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13310",
        "local_instalacao": "AV INDEPENDENCIA QD 18 SENT. NORTE/SUL PLANALTINA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT066.pdf?"
    },
    {
        "identificacao": "RE068",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13004",
        "local_instalacao": "VIA NS 1 QD. 01 FEIRA PLANALTINA SENT. NORTE/ SUL",
        "levantamento_estudo":"https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT068.pdf?"
    },
    {
        "identificacao": "RE069",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13005",
        "local_instalacao": "VIA NS 1 QD 04 CONJUNTO J PLANALTINA SENT SUL/ NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT069.pdf?"
    },
    {
        "identificacao": "RE074",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R12609",
        "local_instalacao": "AV PARANOA QD. 29 CONJ. 21 PARANOA SENT. NORTE/SUL ",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT074.pdf?"
    },
    {
        "identificacao": "RE075",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13006",
        "local_instalacao": "AV. PARANOA QD. 26 CONJ. 20 LT 16 PARANOA SENT. SUL/NORTE ",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT075.pdf?"
    },
    {
        "identificacao": "RE076",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R12610",
        "local_instalacao": "AV PARANOA QD17 CONJ. 11 LT 08 PARANOA SENT NORTE/ SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT076.pdf?"
    },
    {
        "identificacao": "RE077",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13007",
        "local_instalacao": "AV PARANOA QD.12 CONJ. 10 LT 09 PARANOA SENT SUL/ NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT077.pdf?"
    },
    {
        "identificacao": "RE079",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13646",
        "local_instalacao": "AV ALTA TENSAO QD. 02 CONJ. B LOTE 18 SENT. NORTE/SUL - PARANOA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT079.pdf?"
    },
    {
        "identificacao": "RE080",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13647",
        "local_instalacao": "AV. SÃO SEBASTIÃO QD 102 CONJ 04 SÃO SEBASTIÃO SENT. LESTE/OESTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT080.pdf?"
    },
    {
        "identificacao": "RE081",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13648",
        "local_instalacao": "AV. SÃO SEBASTIÃO QD 203 CONJ. 01 SÃO SEBASTIÃO SENT. OESTE/LESTE ",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT081.pdf?"
    },
    {
        "identificacao": "RE082",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13649",
        "local_instalacao": "AV. COMERCIAL ALT. LOTE 1401 PROX. AO BANCO DO BRASIL SENT. NORTE/SUL - SÃO SEBASTIÃO",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT082.pdf?"
    },
    {
        "identificacao": "RE086",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13650/R13666",
        "local_instalacao": "AV ALAGADOS QC 1 ALT DF-483 SANTA MARIA SENTIDO LESTE/OESTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT086.pdf?"
    },
    {
        "identificacao": "RE087",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13651",
        "local_instalacao": "AV. ALAGADOS QC 1 CONJ D PRÓX ADMINISTRAÇÃO SANTA MARIA SENT. OESTE/LESTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT087.pdf?"
    },
    {
        "identificacao": "RE088",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R12690",
        "local_instalacao": "AV. ALAGADOS ALTURA CL 115 SENTIDO LESTE/OESTE SANTA MARIA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT088.pdf?"
    },
    {
        "identificacao": "RE089",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13652",
        "local_instalacao": "AV. ALAGADOS CL 214 SANTA MARIA SENT OESTE/LESTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT089.pdf?"
    },
    {
        "identificacao": "RE090",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13177/R13192",
        "local_instalacao": "AV ELMO SEREJO PROX. A CHÁCARA ONOYAMA TAGUATINGA SENT. LESTE/OESTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT090.pdf?"
    },
    {
        "identificacao": "RE093",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13311",
        "local_instalacao": "SGAN 908 PROX ACESSO VIA W5 SENT. OESTE/LESTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT093.pdf?"
    },
    {
        "identificacao": "RE095",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13178",
        "local_instalacao": "VIA M4 QNM 40 CONJ. E CEILÂNDIA SENT. NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT095.pdf?"
    },
    {
        "identificacao": "RE096",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13179",
        "local_instalacao": "VIA M4 QNM 38 CONJ. G SENT. BR-070 - CEILÂNDIA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT096.pdf?"
    },
    {
        "identificacao": "RE097",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13180",
        "local_instalacao": "VIA M4 QNM 36 CONJ. K SENT. HELIO PRATES CEILÂNDIA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT097.pdf?"
    },
    {
        "identificacao": "RE098",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13181",
        "local_instalacao": "VIA M4 QNM 34 CONJ. K SENT. BR-070 - CEILÂNDIA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT098.pdf?"
    },
    {
        "identificacao": "RE099",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13008",
        "local_instalacao": "VIA P3 QNP 30 CONJ. B CEILÂNDIA SENT. NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT099.pdf?"
    },
    {
        "identificacao": "RE100",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13009",
        "local_instalacao": "VIA P3 QNP 20 CONJ. L CEILÂNDIA SENT. SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT100.pdf?"
    },
    {
        "identificacao": "RE103",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13182",
        "local_instalacao": "VIA P2 QNP 18 CONJ. L CEILÂNDIA SENT. SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT103.pdf?"
    },
    {
        "identificacao": "RE104",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13190",
        "local_instalacao": "VIA P2 QNP 16 CONJ. B SENT. ELMO SEREJO CEILÂNDIA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT104.pdf?"
    },
    {
        "identificacao": "RE105",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R12691",
        "local_instalacao": "AV ELMO SEREJO QNP 20 ALT. CONJ. J CEILÂNDIA SENT. LESTE/OESTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT105.pdf?"
    },
    {
        "identificacao": "RE106",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13012",
        "local_instalacao": "AV. ELMO SEREJO QNP ALT. ADE QD. 3 CONJ. H LOTE 19 - CEILÂNDIA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT106.pdf?"
    },
    {
        "identificacao": "RE107",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13314",
        "local_instalacao": "AV SC 5/AV DOS PIONEIROS QD 05 CONJ F LT 27  GAMA SENT OESTE/LESTE ",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT107.pdf?"
    },
    {
        "identificacao": "RE108",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13315",
        "local_instalacao": "AV SUL QUADRA 36 LOTE 5/6 SENTIDO LESTE/OESTE - GAMA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT108.pdf?"
    },
    {
        "identificacao": "RE109",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13316",
        "local_instalacao": "VIA LESTE INDUSTRIAL/AV ITAMARACA QI 07 LT 830 GAMA SENT NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT109.pdf?"
    },
    {
        "identificacao": "RE110",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13317",
        "local_instalacao": "SETOR INDUSTRIAL QD. 07 LOTE 830 SENT. NORTE/SUL - GAMA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT110.pdf?"
    },
    {
        "identificacao": "RE111",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13318",
        "local_instalacao": "VIA LESTE INDUSTRIAL/AV. ITAMARACA EQ 3/5 UBS 3 GAMA SENT. SUL/NORTE ",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT111.pdf?"
    },
    {
        "identificacao": "RE112",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13319",
        "local_instalacao": "VIA LESTE INDUSTRIAL/AV. ITAMARACA QI 07 LOTE 1240 GAMA SENT. NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT112.pdf?"
    },
    {
        "identificacao": "RE113",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13653",
        "local_instalacao": "2ª AVENIDA NORTE QR 614 PRÓX. AO HRSAM SENT. LESTE/OESTE SAMAMBAIA ",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT113.pdf?"
    },
    {
        "identificacao": "RE114",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13312",
        "local_instalacao": "2ª AVENIDA NORTE QR 412/414 SENT. OESTE/LESTE - SAMAMBAIA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT114.pdf?"
    },
    {
        "identificacao": "RE116",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13654",
        "local_instalacao": "AV. SANTA MARIA QC 03 CL 410 PROX. VILA OLÍMPICA SANTA MARIA SENT. OESTE/LESTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT116.pdf?"
    },
    {
        "identificacao": "RE117",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13655",
        "local_instalacao": "AV. SANTA MARIA CL 312 LT E SANTA MARIA SENT. LESTE/OESTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT117.pdf?"
    },
    {
        "identificacao": "RE118",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13320",
        "local_instalacao": "VIA HCE 1 TERRAÇO SHOPPING SENT. OCTOGONAL/EPIA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT118.pdf?"
    },
    {
        "identificacao": "RE119",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13321",
        "local_instalacao": "VIA HCE 1 TERRAÇO SHOPPING SENT. OCTOGONAL/ EPIG",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT119.pdf?"
    },
    {
        "identificacao": "RE120",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13322",
        "local_instalacao": "VIA DE LIGACAO PONTE DAS GARCAS SENT PLANO PILOTO/ LAGO SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT120.pdf?"
    },
    {
        "identificacao": "RE121",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13323",
        "local_instalacao": "VIA DE LIGACAO PONTE DAS GARÇAS SENT LAGO SUL/ PLANO PILOTO",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT121.pdf?"
    },
    {
        "identificacao": "RE122",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13010",
        "local_instalacao": "VIA DE LIGAÇÃO L-2 / PONTE COSTA E SILVA SENT. PLANO PILOTO/LAGO SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT122.pdf?"
    },
    {
        "identificacao": "RE123",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13011",
        "local_instalacao": "VIA DE LIG EPDB / PONTE COSTA E SILVA SENT LAGO SUL/ P. PILOTO",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT123.pdf?"
    },
    {
        "identificacao": "RE126",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13185",
        "local_instalacao": "VIA LJ-1 QNL 2 BL A TAGUATINGA SENT SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT126.pdf?"
    },
    {
        "identificacao": "RE127",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R12692",
        "local_instalacao": "VIA LJ-2 QNJ 58 BL. E TAGUATINGA SENT SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT127.pdf?"
    },
    {
        "identificacao": "RE128",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13324",
        "local_instalacao": "AV. INDEPENDENCIA SR JARDIM RORIZ QD 01 CONJ 1A PLANALTINA SENT SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT128.pdf?"
    },
    {
        "identificacao": "RE133",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13014/R13013",
        "local_instalacao": "VIA JK PROX. PONTE JK SENT. PLANO PILOTO / LAGO SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT133.pdf?"
    },
    {
        "identificacao": "RE134",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13325/R13331",
        "local_instalacao": "VIA JK PROX. A PONTE JK SENT. LAGO SUL / PLANO PILOTO",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT134.pdf?"
    },
    {
        "identificacao": "RE135",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13186/R13193",
        "local_instalacao": "VIA LJ-1 QNL 1 CENTRO EDUCACIONAL 06 TAGUATINGA SENT. NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT135.pdf?"
    },
    {
        "identificacao": "RE138",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13187/R13194",
        "local_instalacao": "VIA LJ-2 QNL 23 BL. A TAGUATINGA SENT. NORTE/SUL ",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT138.pdf?"
    },
    {
        "identificacao": "RE139",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13329",
        "local_instalacao": "AV. ELMO SEREJO PROX. KIREYBARA SENT. OESTE/LESTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT139.pdf?"
    },
    {
        "identificacao": "RE140",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13326",
        "local_instalacao": "AV. CONTORNO SETOR OESTE ALT. QD. 24 SENT. NORTE(BRT) - GAMA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT140.pdf?"
    },
    {
        "identificacao": "RE144",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13003",
        "local_instalacao": "VIA T-1 / AV. CENTRAL QD. 301 PROX. A ADMINISTRAÇÃO SAMAMBAIA SENT. SUL/NORTE ",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT144.pdf?"
    },
    {
        "identificacao": "RE145",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13173",
        "local_instalacao": "CENTRO URBANO ALT. QD. 301 EM FRENTE A ADMINISTRAÇÃO SENT. SUL - SAMAMBAIA",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT145.pdf?"
    },
    {
        "identificacao": "RE146",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13189",
        "local_instalacao": "2ª AV. NORTE QS 604 PROX. EC 604 SAMAMBAIA SENT. LESTE/OESTE ",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT146.pdf?"
    },
    {
        "identificacao": "RE147",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13170",
        "local_instalacao": "2ª AV. NORTE QN 404 CONJ. D SAMAMBAIA SENT. OESTE / LESTE  ",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT147.pdf?"
    },
    {
        "identificacao": "RE148",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13656",
        "local_instalacao": "AV. MANGUEIRAL ALT. QC 10 JARDIM BOTANICO SENT. OESTE/LESTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT148.pdf?"
    },
    {
        "identificacao": "RE149",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13657",
        "local_instalacao": "AV. MANGUEIRAL ALT. QC 14 JARDIM BOTANICO SENT. OESTE/LESTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT149.pdf?"
    },
    {
        "identificacao": "RE150",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13658/R13667",
        "local_instalacao": "AV. CONTORNO QE 15 CONJ. E GUARÁ II SENT. HORÁRIO ",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT150.pdf?"
    },
    {
        "identificacao": "RE151",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13668/R13659",
        "local_instalacao": "AV. CONTORNO QE 23/25 PROX. CAVE GUARÁ II SENT. ANTI-HORÁRIO ",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT151.pdf?"
    },
    {
        "identificacao": "RE152",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R07141",
        "local_instalacao": "VIA BERNARDO SAYÃO SRIA QE 38/40 POLO DE MODA GUARÁ II SENT. NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT152.pdf?"
    },
    {
        "identificacao": "RE153",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R07142",
        "local_instalacao": "SRIA QE 38 GUARÁ II SENT. GUARÁ II",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT153.pdf?"
    },
    {
        "identificacao": "RE154",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13660",
        "local_instalacao": "VIA MN2 QNM 07 CONJ. A LT. 46 CEILÂNDIA SENT. SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT154.pdf?"
    },
    {
        "identificacao": "RE155",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13176",
        "local_instalacao": "VIA MN2 QNM 03 CONJ. A CEILÂNDIA SENT. SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT155.pdf?"
    },
    {
        "identificacao": "RE156",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R12999",
        "local_instalacao": "VIA MN2 QNM 02 CONJ. A CEILÂNDIA SENT. NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT156.pdf?"
    },
    {
        "identificacao": "RE157",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13000",
        "local_instalacao": "VIA SCN QD. 54 LT. 07 SETOR CENTRAL GAMA SENT. LESTE/OESTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT157.pdf?"
    },
    {
        "identificacao": "RE158",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13661",
        "local_instalacao": "AV. ALAGADOS CL 202 PROX. HOSPITAL REGIONAL DE SANTA MARIA SENT. SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT158.pdf?"
    },
    {
        "identificacao": "RE159",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13002",
        "local_instalacao": "AV. CONTORNO SETOR OESTE PROX. QD. 14 GAMA SENT. NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT159.pdf?"
    },
    {
        "identificacao": "RE160",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13662",
        "local_instalacao": "AV DOS BOMBEIROS Q. 02 PROX RESIDENCIAL GAMAGGIORE GAMA SENT NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT160.pdf?"
    },
    {
        "identificacao": "RE161",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13663",
        "local_instalacao": "AV. DO SOL PROX RUA 101 COND. QUINTAS DO SOL JARDIM BOTÂNICO SENT. SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT161.pdf?"
    },
    {
        "identificacao": "RE162",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13327",
        "local_instalacao": "AV. INDEPENDENCIA SETOR COMERCIAL QUADRA 02, BLOCO H, PLANALTINA SENT. SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT162.pdf?"
    },
    {
        "identificacao": "RE163",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13183",
        "local_instalacao": "VIA N3 EQNN 21/23 CEILÂNDIA SENTIDO SUL/NORTE",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT163.pdf?"
    },
    {
        "identificacao": "RE164",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13184",
        "local_instalacao": "VIA N3 QNN 31 UNIVERSIDADE IESB CEILÂNDIA SENTIDO NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT164.pdf?"
    },
    {
        "identificacao": "RE165",
        "tipo": "DETRAN - LOMBADA ELETRÔNICA",
        "numero_serie": "R13309",
        "local_instalacao": "AV INDEPENDÊNCIA QD H CJ H5 VILA NOSSA SENHORA DE FÁTIMA SENT NORTE/SUL",
        "levantamento_estudo": "https://geoservicos.detran.df.gov.br/geoserver/styles/equipamentos/barreira/ldt/LDT165.pdf?"
    }
];